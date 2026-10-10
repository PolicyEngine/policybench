"""Checks that published note prose stays tied to committed evidence."""

from __future__ import annotations

import csv
import gzip
import json
import re
import sys
from collections import Counter
from datetime import date, datetime, timezone
from functools import cache
from pathlib import Path
from statistics import median

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
# `{key}`, or `{key:words}`, which the app renders as a word for a whole
# number under ten (NotesContent.tsx).
PLACEHOLDER = re.compile(r"\{([A-Za-z][A-Za-z0-9]*)(?::words)?\}")

csv.field_size_limit(sys.maxsize)


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def _note(slug: str) -> dict:
    return _load_json(NOTES_DIR / f"{slug}.json")


SNAPSHOT_DIR = ROOT / "paper/snapshot/20260501"


@cache
def _payload_at(root: Path) -> dict:
    """The run payload of the snapshot tree under ``root`` (this checkout, or
    a commit's snapshot from ``_snapshot_root``)."""
    return read_run_payload(_in(root, RUN_DIR))


@cache
def _dashboard() -> dict:
    return _payload_at(ROOT)


@cache
def _frozen_release() -> str:
    manifest = _load_json(ROOT / "paper/snapshot/20260501/manifest.json")
    return manifest["published_dashboard_artifact"]["tag"]


def _in(root: Path, path: Path) -> Path:
    """A snapshot file as the tree under ``root`` holds it."""
    assert path.is_relative_to(SNAPSHOT_DIR), path
    return root / path.relative_to(ROOT)


@cache
def _snapshot_root(commit: str) -> Path:
    """A scratch tree holding paper/snapshot/20260501 exactly as ``commit`` has
    it, removed when the session exits. CI checks out full history."""
    import atexit
    import shutil
    import subprocess
    import tempfile

    def git(*args: str) -> bytes:
        shown = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)
        assert shown.returncode == 0, (
            f"the snapshot at {commit[:8]} needs git history; fetch full "
            "history. " + shown.stderr.decode()
        )
        return shown.stdout

    snapshot = SNAPSHOT_DIR.relative_to(ROOT).as_posix()
    listed = git("ls-tree", "-r", "--name-only", commit, snapshot)
    root = Path(tempfile.mkdtemp(prefix=f"policybench-snapshot-{commit[:8]}-"))
    atexit.register(shutil.rmtree, root, ignore_errors=True)
    for name in listed.decode().splitlines():
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(git("show", f"{commit}:{name}"))
    return root


def _release_tag(root: Path) -> str:
    """The tag the snapshot under ``root`` freezes, after checking that its
    manifest pins the payload the tree holds."""
    manifest = _load_json(_in(root, SNAPSHOT_DIR / "manifest.json"))
    payload = run_payload_path(_in(root, RUN_DIR))
    assert manifest["files"] == [
        {
            "path": payload.relative_to(_in(root, SNAPSHOT_DIR)).as_posix(),
            "sha256": _sha256_file(payload),
        }
    ]
    return manifest["published_dashboard_artifact"]["tag"]


# A note keeps the release its facts were checked against. Facts of a note on
# the frozen release are recomputed from this checkout's snapshot. A note on a
# superseded release whose freezing commit RELEASE_COMMITS names is recomputed
# from the snapshot that commit holds; an older one keeps the facts verified
# when its release was frozen (git history holds the run).
SUPERSEDED_RELEASES = {
    "dashboard-data-20260901c": "2026-09-01",
    "dashboard-data-20260905c": "2026-09-05",
    # Superseded by dashboard-data-20260922b, which excluded one more output
    # (scenario_045 SNAP, root cause r33) on the same 42-model snapshot.
    "dashboard-data-20260922": "2026-09-22",
    # Superseded by dashboard-data-20260922c, which regenerates that output
    # with r33's fix (policyengine-us#9586, merged 2026-09-24).
    "dashboard-data-20260922b": "2026-09-22",
    # Superseded by dashboard-data-20260929, which adds three models and moves
    # the references to policyengine-us 2.15.17.
    "dashboard-data-20260922c": "2026-09-22",
    # Superseded by dashboard-data-20260930, which adds GPT-6.1 Sol on the
    # same references and exclusions. Its note's facts are still recomputed,
    # from the snapshot its own commit holds (RELEASE_20260929_COMMIT).
    "dashboard-data-20260929": "2026-09-29",
    # Superseded by dashboard-data-20261006, which stops scoring eight tax
    # outputs on the same references, predictions and board snapshot. The
    # October 5 BBCE note's facts are still recomputed, from the snapshot its
    # commit holds (RELEASE_20260930_COMMIT).
    "dashboard-data-20260930": "2026-09-30",
    # Superseded by dashboard-data-20261009, which adds Claude Haiku 5.5 and
    # moves the references to the policyengine-us release that fixes engine
    # defects behind exclusions. Its note's facts are still recomputed, from
    # the snapshot its commit holds (RELEASE_20261006_COMMIT).
    "dashboard-data-20261006": "2026-09-30",
}
# The frozen release's board snapshot is its manifest's snapshot date.
CURRENT_RELEASE_SNAPSHOT = json.loads((SNAPSHOT_DIR / "manifest.json").read_text())[
    "snapshot_date"
]
# The commit that froze each superseded release whose notes' facts are
# recomputed from git: the merges of #182, #187 and #202.
RELEASE_20260929_COMMIT = "d616e67c33b6f80dabf5cb7329f069f9a1de069d"
RELEASE_20260930 = "dashboard-data-20260930"
RELEASE_20260930_COMMIT = "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"
RELEASE_20261006_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"
RELEASE_COMMITS = {
    "dashboard-data-20260929": RELEASE_20260929_COMMIT,
    "dashboard-data-20260930": RELEASE_20260930_COMMIT,
    "dashboard-data-20261006": RELEASE_20261006_COMMIT,
}


def _paper_snapshot(release: str) -> dict:
    """app/src/paperSnapshot.json as ``release`` left it: at its commit when
    it is superseded, this checkout's while it is the frozen release."""
    import subprocess

    if release not in RELEASE_COMMITS:
        return _load_json(ROOT / "app/src/paperSnapshot.json")
    shown = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "show",
            f"{RELEASE_COMMITS[release]}:app/src/paperSnapshot.json",
        ],
        capture_output=True,
    )
    assert shown.returncode == 0, shown.stderr.decode()
    return json.loads(shown.stdout)


def _release_root(release: str) -> Path:
    """A tree holding paper/snapshot/20260501 as ``release`` froze it: the
    snapshot of its commit when it is superseded, this checkout while it is
    the frozen release. Checks that the tree's manifest names the release."""
    if release in RELEASE_COMMITS:
        root = _snapshot_root(RELEASE_COMMITS[release])
    else:
        assert release == _frozen_release(), (
            f"{release} is superseded; add the commit that froze it to RELEASE_COMMITS"
        )
        root = ROOT
    assert _release_tag(root) == release
    return root


@cache
def _snap_predictions() -> dict[str, list[dict[str, str]]]:
    rows = {model: [] for model in TOP_MODELS}
    with gzip.open(PREDICTIONS_PATH, "rt", encoding="utf-8", newline="") as source:
        for row in csv.DictReader(source):
            if row["variable"] == "snap" and row["model"] in rows:
                rows[row["model"]].append(row)
    assert all(len(model_rows) == 100 for model_rows in rows.values())
    return rows


def _snap_references(path: Path = REFERENCES_PATH) -> dict[str, float]:
    with path.open(encoding="utf-8", newline="") as source:
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


def _gpt6_sol_facts() -> dict:
    """The GPT-6 Sol note's facts, computed on the frozen snapshot."""
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
    for row in (sol, opus, luna):
        assert row["nParsed"] == row["n"]
    return derived


def test_gpt6_sol_note_facts() -> None:
    note = _note(SOL6_NOTE)
    if not _recompute_against_frozen_snapshot(note):
        return
    assert note["facts"] == _gpt6_sol_facts()


def _reference_audit_facts() -> dict:
    """The reference audit note's facts, computed on the frozen snapshot."""
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
    return derived


def test_reference_audit_note_facts() -> None:
    note = _note(AUDIT_NOTE)
    if not _recompute_against_frozen_snapshot(note):
        return
    assert note["facts"] == _reference_audit_facts()


BBCE_NOTE = "2026-10-05-five-snap-households-bbce"
# The note's earlier version, first published September 23 and replaced by
# the October 5 note; /notes/<this slug> redirects to the October 5 note
# (app/next.config.ts). Git history holds each of its versions.
BBCE_NOTE_EARLIER = "2026-09-23-five-snap-households-bbce"
BBCE_NOTE_EARLIER_PATH = f"app/src/notes/{BBCE_NOTE_EARLIER}.json"
# The commit that first published it (PR #175), counting the Michigan worker,
# and the commit of its next version (PR #177), which no longer counts them.
BBCE_NOTE_FIRST_COMMIT = "a6379216f6fd4bbc8d25e297db2bae1db1535a64"
BBCE_NOTE_REVISED_COMMIT = "ba886b4cfa69b631df59f49e277e4a6c22832116"
PATHWAYS_0922_PATH = ROOT / "notes/data/snap_pathways_20260922.csv"
PATHWAYS_0922_META_PATH = PATHWAYS_0922_PATH.with_suffix(
    PATHWAYS_0922_PATH.suffix + ".meta.json"
)
PATHWAYS_0930_PATH = ROOT / "notes/data/snap_pathways_20260930.csv"
PATHWAYS_0930_META_PATH = PATHWAYS_0930_PATH.with_suffix(
    PATHWAYS_0930_PATH.suffix + ".meta.json"
)
BBCE_ROWS_PATH = ROOT / "notes/data/bbce_households_20260930.csv"
BBCE_ROWS_META_PATH = BBCE_ROWS_PATH.with_suffix(BBCE_ROWS_PATH.suffix + ".meta.json")
BBCE_ASSET_ROWS_PATH = ROOT / "notes/data/bbce_asset_households_20260930.csv"
BBCE_ASSET_ROWS_META_PATH = BBCE_ASSET_ROWS_PATH.with_suffix(
    BBCE_ASSET_ROWS_PATH.suffix + ".meta.json"
)
# The modules the references' configuration composes (latest_final), and the
# sales tax table one of them reads, which the pathway meta pins.
REFERENCE_FIX_DIR = ROOT / "reference_audit/2026-09-28/fixes"
SALES_TAX_TABLE = ROOT / "reference_audit/2026-09-22/fixes/r19_irs_sales_tax_2025.json"
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
    "AZ": "Arizona",
    "CA": "California",
    "CO": "Colorado",
    "CT": "Connecticut",
    "MA": "Massachusetts",
    "MI": "Michigan",
    "MN": "Minnesota",
    "NC": "North Carolina",
    "NJ": "New Jersey",
    "NY": "New York",
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


def _snap_output_references(
    variable: str, path: Path = REFERENCES_PATH
) -> dict[str, float]:
    with path.open(encoding="utf-8", newline="") as source:
        return {
            row["scenario_id"]: float(row["value"])
            for row in csv.DictReader(source)
            if row["variable"] == variable
        }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def _scenario_inputs(run_dir: Path = RUN_DIR) -> dict[str, dict]:
    """Each household's frozen scenario: people with their inputs, and units."""
    return {
        row["scenario_id"]: json.loads(row["scenario_json"])
        for row in _read_csv(run_dir / "scenarios.csv")
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


def _git_json(commit: str, path: str) -> dict:
    """A JSON file as a commit in the repository's history holds it."""
    import subprocess

    shown = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{path}"], capture_output=True
    )
    assert shown.returncode == 0, (
        f"{path} at {commit[:8]} needs git history; fetch full history. "
        + shown.stderr.decode()
    )
    return json.loads(shown.stdout)


def _check_committed_rows(
    rows: list[dict],
    path: Path,
    meta_path: Path,
    households: list[str],
    patterns: dict[str, str],
    rows_release: str,
    root: Path,
) -> None:
    """The committed rows are the regenerated rows, from the payload of the
    snapshot under ``root`` and the committed pathway recomputation, with the
    note's own mention patterns. The rows record the release they were built
    on, ``rows_release``; when the tree is that release, its payload and its
    manifest's asset are the ones the meta pins."""
    assert _read_csv(path) == [
        {key: str(value) for key, value in row.items()} for row in rows
    ]
    meta = _load_json(meta_path)
    assert meta["households"] == households
    assert meta["mention_patterns"] == patterns
    assert meta["release"] == rows_release
    if _release_tag(root) == rows_release:
        # The rows come from the committed run payload; the release asset is
        # a different file carrying the same US payload, pinned by the
        # manifest.
        run_payload = run_payload_path(_in(root, RUN_DIR))
        assert meta["run_payload_sha256"] == _sha256_file(run_payload)
        manifest = _load_json(_in(root, SNAPSHOT_DIR / "manifest.json"))
        assert (
            meta["release_payload_sha256"]
            == manifest["published_dashboard_artifact"]["sha256"]
        )
    assert meta["pathways"] == PATHWAYS_0930_PATH.relative_to(ROOT).as_posix()
    assert meta["pathways_sha256"] == _sha256_file(PATHWAYS_0930_PATH)
    assert meta["rows"] == len(rows)


def _months(row: dict[str, str], column: str) -> list[float]:
    """A pathway row's monthly values, January to December."""
    values = [float(value) for value in row[column].split()]
    assert len(values) == 12
    return values


def test_bbce_households_note_facts() -> None:
    """The October 5 BBCE note: its facts recompute from the snapshot of its
    release, as the release's commit holds it, and the committed pathway
    recomputation on the references' engine, and every sentence is pinned
    beside its evidence. Its closing paragraph, on the later release, is
    test_bbce_note_describes_the_later_release's."""
    note = _note(BBCE_NOTE)
    assert note["date"] == "2026-10-05"
    assert not (NOTES_DIR / f"{BBCE_NOTE_EARLIER}.json").exists()
    # The links, whatever release is frozen: every note link resolves to a
    # note and none to the earlier slug, every repository link resolves to a
    # committed file, and the release and pull request links are the note's.
    links = {entry["label"]: entry["href"] for entry in note["data"]}
    blob = "https://github.com/PolicyEngine/policybench/blob/main/"
    for href in links.values():
        assert BBCE_NOTE_EARLIER not in href
        if href.startswith("/notes/"):
            assert (NOTES_DIR / f"{href.removeprefix('/notes/')}.json").is_file()
        if href.startswith(blob):
            assert (ROOT / href.removeprefix(blob)).is_file(), href
    assert links["Dashboard data release"] == (
        "https://github.com/PolicyEngine/policybench/releases/tag/" + note["release"]
    )
    for number, topic in (
        ("9162", "SNAP minimum rounding"),
        ("9586", "SNAP child support treatment"),
        ("9671", "SNAP farm rent"),
    ):
        assert links[f"policyengine-us #{number} ({topic})"] == (
            f"https://github.com/PolicyEngine/policyengine-us/pull/{number}"
        )
    # The September 29 release note links this one under its date (the
    # September 3 and September 22 notes' tests pin their links to it).
    release_links = {e["label"]: e["href"] for e in _note(RELEASE_NOTE)["data"]}
    assert (
        release_links[
            "Note on the SNAP households that qualify through BBCE "
            f"({_month_day(note['date'])})"
        ]
        == f"/notes/{BBCE_NOTE}"
    )
    # The note keeps release 20260930, and its facts recompute from that
    # release's snapshot whatever release is frozen. The later release's
    # facts are the closing paragraph's.
    assert note["release"] == RELEASE_20260930
    assert note["boardSnapshot"] == SUPERSEDED_RELEASES[note["release"]]
    later = _later_facts(note)
    assert {k: v for k, v in note["facts"].items() if k not in later} == (
        _bbce_facts_at(note["release"])
    )


# The opening of a closing paragraph that describes a later release.
LATER_RELEASE_OPENING = "A later release, "


def _bbce_note_facts(note: dict, root: Path) -> dict:
    """The BBCE note's facts, recomputed from the snapshot under ``root`` and
    the committed pathway recomputation, with every sentence but the closing
    later-release paragraph pinned beside its evidence. Every check holds on
    any release whose references, predictions and SNAP exclusions are the
    note's release's, so the later release's figures recompute here too."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from bbce_households_20260930 import (
        BBCE_PATTERN,
        asset_households,
        bbce_households,
        build,
    )

    from policybench.paper_results import MODEL_DISPLAY_NAMES

    links = {entry["label"]: entry["href"] for entry in note["data"]}
    blob = "https://github.com/PolicyEngine/policybench/blob/main/"
    run_dir = _in(root, RUN_DIR)
    references_path = _in(root, REFERENCES_PATH)
    payload = _payload_at(root)
    references = _snap_references(references_path)
    exclusions = _load_json(_in(root, EXCLUSIONS_PATH))["exclusions"]
    snap_exclusions = {
        e["scenario_id"]: e for e in exclusions if e["variable"] == "snap"
    }
    reference_meta = _load_json(_in(root, REFERENCE_META_PATH))
    upgrade = next(
        r for r in reference_meta["revisions"] if r.get("kind") == "engine_upgrade"
    )
    engine = upgrade["engine_version"].removeprefix("policyengine-us ")
    scenarios = _scenario_inputs(run_dir)
    paragraphs = [
        p for p in note["paragraphs"] if not p.startswith(LATER_RELEASE_OPENING)
    ]
    assert paragraphs == note["paragraphs"][: len(paragraphs)]
    text = " ".join(paragraphs)

    # Every sentence of the note is pinned in full beside the evidence for it,
    # so a changed claim or a moved placeholder fails; the check at the end
    # fails on any sentence left unpinned.
    pinned: list[str] = []

    def pin(*sentences: str) -> None:
        for sentence in sentences:
            assert text.count(sentence) == 1, sentence
            pinned.append(sentence)

    # The committed pathway recomputation is tied to these references: it
    # reproduces every scored SNAP reference, and it ran on the committed
    # scenarios and references with the modules the references were built
    # with, on the engine they were built on.
    pathways = _read_csv(PATHWAYS_0930_PATH)
    pathway_meta = _load_json(PATHWAYS_0930_META_PATH)
    assert len(pathways) == 100
    for row in pathways:
        scenario_id = row["scenario_id"]
        assert float(row["snap_reference"]) == references[scenario_id]
        assert (row["snap_scored"] == "True") == (scenario_id not in snap_exclusions)
        if row["snap_scored"] == "True":
            assert abs(float(row["snap_recomputed"]) - references[scenario_id]) <= 1
        assert (
            abs(sum(_months(row, "monthly_snap")) - float(row["snap_recomputed"]))
            < 0.01
        )
    assert pathway_meta["reference_csv_sha256"] == _sha256_file(references_path)
    assert pathway_meta["scenarios_sha256"] == _sha256_file(run_dir / "scenarios.csv")
    assert (
        pathway_meta["fix_module"] == "reference_audit/2026-09-28/fixes/latest_final.py"
    )
    assert pathway_meta["fix_modules_sha256"] == {
        **{
            path.name: _sha256_file(path)
            for path in sorted(REFERENCE_FIX_DIR.glob("*.py"))
        },
        SALES_TAX_TABLE.name: _sha256_file(SALES_TAX_TABLE),
    }
    for module in upgrade["fix_modules"]:
        assert pathway_meta["fix_modules_sha256"][module["module"]] == module["sha256"]
    assert (
        pathway_meta["policyengine_us_version"]
        == engine
        == reference_meta["policyengine_bundles"]["us"]["model_version"]
    )
    assert set(pathway_meta["excluded_snap_rows"]["households"]) == set(snap_exclusions)
    by_id = {row["scenario_id"]: row for row in pathways}
    rules = pathway_meta["engine_rules"]

    # The households: derived from the recomputation month by month, and
    # every model's answer for each, regenerated from the payload with the
    # note's mention patterns and compared with the committed rows.
    regexes = note["mentionRegexes"]
    assert regexes["bbce"] == BBCE_PATTERN
    # "Assets" is the September 3 note's pattern.
    previous = _note(SNAP_NOTE)
    assert regexes["assets"] == previous["mentionRegexes"]["assets"]
    built = build(payload, pathways)
    for path, meta_path in (
        (BBCE_ROWS_PATH, BBCE_ROWS_META_PATH),
        (BBCE_ASSET_ROWS_PATH, BBCE_ASSET_ROWS_META_PATH),
    ):
        built_rows, built_households, built_patterns = built[path]
        _check_committed_rows(
            built_rows,
            path,
            meta_path,
            built_households,
            built_patterns,
            note["release"],
            root,
        )
    rows, households, income_patterns = built[BBCE_ROWS_PATH]
    asset_rows, savings_households, asset_patterns = built[BBCE_ASSET_ROWS_PATH]
    assert households == bbce_households(pathways)
    assert savings_households == asset_households(pathways)
    assert income_patterns == {
        "mentions_categorical_eligibility": regexes["bbce"],
        "mentions_net_income_limit": regexes["netLimit"],
    }
    assert asset_patterns == {
        "mentions_categorical_eligibility": regexes["bbce"],
        "mentions_assets": regexes["assets"],
    }
    states = {s: payload["scenarios"][s]["state"] for s in households}
    assert states == {
        "scenario_013": "AZ",
        "scenario_027": "CT",
        "scenario_030": "TX",
        "scenario_073": "MI",
        "scenario_108": "WI",
    }
    arizona, couple_id, texas_id, michigan_id, wisconsin_id = households
    names = {s: STATE_NAMES[state] for s, state in states.items()}
    assert not set(households) & set(savings_households)

    # The correct amounts: the minimum benefit in each month the household
    # qualifies and $0 in each other month. Four qualify all year; the
    # Arizona household from March.
    income_group = [by_id[s] for s in households]
    eligible_months = {
        s: [
            i
            for i, p in enumerate(by_id[s]["pathway_by_month"].split())
            if p != "ineligible"
        ]
        for s in households
    }
    minimums = {
        value for row in income_group for value in _months(row, "monthly_min_allotment")
    }
    assert len(minimums) == 1
    minimum = minimums.pop()
    for scenario_id in households:
        row = by_id[scenario_id]
        snap = _months(row, "monthly_snap")
        assert snap == [
            minimum if i in eligible_months[scenario_id] else 0 for i in range(12)
        ]
        assert references[scenario_id] == minimum * len(eligible_months[scenario_id])
    full_year = [s for s in households if len(eligible_months[s]) == 12]
    assert full_year == [couple_id, texas_id, michigan_id, wisconsin_id]
    assert {references[s] for s in full_year} == {12 * minimum}
    reference_amount = 12 * minimum
    # March to December: months 3 to 12.
    assert eligible_months[arizona] == list(range(2, 12))
    # BBCE leaves the benefit formula in place: in 2.15.17, snap_normal_allotment
    # pays the larger of the minimum and the maximum allotment less the
    # expected contribution (30% of net income) to every eligible household,
    # whichever way it qualifies. At these incomes the formula pays nothing.
    assert (
        "normal_allotment = max_allotment - expected_contribution"
        in (rules["snap_normal_allotment"])
    )
    assert (
        "return max_(min_allotment, normal_allotment)"
        in (rules["snap_normal_allotment"])
    )
    for scenario_id in households:
        row = by_id[scenario_id]
        for i in eligible_months[scenario_id]:
            assert (
                _months(row, "monthly_expected_contribution")[i]
                >= _months(row, "monthly_max_allotment")[i]
            )
    # SNAP pays every eligible household of one or two people at least the
    # minimum, and larger households none (7 CFR 273.10(e)(2)(ii)(C)). New
    # Jersey, Maryland and DC set their own minimums. The engine sizes the
    # SNAP unit, which can leave out a member of the household: one household
    # of three (scenario_123, ineligible all year) has a SNAP unit of two, with
    # the two-person maximum allotment, and so the minimum.
    federal_minimum = [
        row for row in pathways if row["state"] not in {"NJ", "MD", "DC"}
    ]
    two_person_max = _months(by_id[couple_id], "monthly_max_allotment")
    for row in federal_minimum:
        small = int(row["household_size"]) <= 2
        unit_of_two = _months(row, "monthly_max_allotment") == two_person_max
        assert _months(row, "monthly_min_allotment") == (
            [minimum if small or unit_of_two else 0] * 12
        )
    assert {
        row["scenario_id"]
        for row in federal_minimum
        if int(row["household_size"]) > 2
        and _months(row, "monthly_min_allotment")[0] > 0
    } == {"scenario_123"}
    assert set(by_id["scenario_123"]["pathway_by_month"].split()) == {"ineligible"}
    for row in pathways:
        if int(row["household_size"]) <= 2:
            assert all(
                value == 0 or value >= floor
                for value, floor in zip(
                    _months(row, "monthly_snap"),
                    _months(row, "monthly_min_allotment"),
                    strict=True,
                )
            )
    # The minimum in these states under the law, and in the references. The
    # references follow law published before the reference freeze; USDA
    # published FY2027, which raises the minimum from October 2026, after
    # it. So the references hold the FY2026 schedule, the minimum among it,
    # for October to December 2026 (convention c_snap_hold_fy2026), and the
    # minimum is the same in every month of the recomputation above.
    hold = next(
        r
        for r in reference_meta["revisions"]
        if r.get("convention") == "c_snap_hold_fy2026"
    )
    freeze = re.search(
        r"law published before the (\d{4}-\d{2}-\d{2}) reference freeze", hold["rule"]
    )
    fy2027 = re.search(r"USDA published FY2027 on (\d{4}-\d{2}-\d{2})", hold["rule"])
    assert freeze is not None and fy2027 is not None
    assert freeze.group(1) < fy2027.group(1)
    # The engine upgrade keeps that cutoff for the references it rebuilt.
    assert (
        f"law published before the {freeze.group(1)} reference freeze"
        in upgrade["rule"]
    )
    assert freeze.group(1) < upgrade["date"]
    # Re-expressed for 2.15.17, as one of the references' modules (above),
    # the convention holds the minimum's published adjustment, with the
    # rest of the FY2027 schedule, from October to December 2026 only.
    import ast

    hold_module = "latest_c_snap_hold_fy2026.py"
    assert hold_module in {m["module"] for m in upgrade["fix_modules"]}
    assigned = {
        node.targets[0].id: node.value
        for node in ast.parse((REFERENCE_FIX_DIR / hold_module).read_text()).body
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
    }
    assert "gov.usda.snap.min_allotment.published_adjustment" in ast.literal_eval(
        assigned["HOLD_NODES"]
    )
    assert [ast.literal_eval(assigned[k].args[0]) for k in ("START", "STOP")] == [
        "2026-10-01",
        "2026-12-31",
    ]
    held_months = [9, 10, 11]
    # policyengine-us 2.15.17 as released, without the convention, pays each
    # of the five $1 a month more in each held month (the upgrade's sweep of
    # raw 2.15.17), and each qualifies in all three.
    sweep = {
        row["scenario_id"]: row
        for row in _read_csv(ROOT / "reference_audit/2026-09-28/sweep_moves.csv")
        if row["variable"] == "snap"
    }
    raw_gaps = set()
    for scenario_id in households:
        assert float(sweep[scenario_id]["reference"]) == references[scenario_id]
        assert set(held_months) <= set(eligible_months[scenario_id])
        raw = float(sweep[scenario_id]["raw_2_15_17"])
        raw_gaps.add((raw - references[scenario_id]) / len(held_months))
    (raw_gap,) = raw_gaps
    minimum_from_october = minimum + raw_gap
    # The engine's own parameters give the two minimums: 8% of the
    # one-person maximum, rounded to the dollar, plus the adjustment USDA's
    # FY2027 figures need (7 U.S.C. 2017(a); FY2026 $298 and $24, FY2027
    # $306 and $25, as USDA published them). Read from the installed engine
    # when it is the references' engine, which the repository pins.
    from importlib.metadata import PackageNotFoundError, version
    from importlib.util import find_spec

    try:
        installed = version("policyengine-us")
    except PackageNotFoundError:
        installed = None
    # The engine's minimum by fiscal year, read below when the installed
    # engine is the references'.
    engine_minimums: dict[int, int] | None = None
    if installed == engine:
        import yaml

        engine_dir = Path(find_spec("policyengine_us").origin).parent
        snap_dir = engine_dir / "parameters/gov/usda/snap"

        def _parameter(name: str) -> dict:
            return yaml.safe_load((snap_dir / name).read_text())

        (rate,) = _parameter("min_allotment/rate.yaml")["values"].values()
        one_person = _parameter("max_allotment.yaml")["main"]["CONTIGUOUS_US"][1]
        adjustment = _parameter("min_allotment/published_adjustment.yaml")[
            "CONTIGUOUS_US"
        ]
        # The adjustment is 0 from 2015 until FY2027, so a fiscal year without
        # its own entry takes 0.
        assert [k for k in adjustment if k.year < 2026] == [date(2015, 10, 1)]
        engine_minimums = {
            fiscal_year: round(rate * one_person[date(fiscal_year - 1, 10, 1)])
            + adjustment.get(date(fiscal_year - 1, 10, 1), 0)
            for fiscal_year in (2024, 2025, 2026, 2027)
        }
        assert engine_minimums[2026] == minimum
        assert engine_minimums[2027] == minimum_from_october
        assert one_person[date(2025, 10, 1)] == 298
        assert adjustment[date(2026, 10, 1)] == 1
        # The engine rounds 8% of the one-person maximum to the dollar, as
        # SNAP does (policyengine-us#9162).
        min_allotment_source = (
            engine_dir / "variables/gov/usda/snap/snap_min_allotment.py"
        ).read_text()
        assert "np.round(min_allotment.rate * relevant_max_allotment)" in (
            min_allotment_source
        )
    # None of the five is in a state with its own minimum or its own maximum.
    assert not {states[s] for s in households} & {"AK", "HI", "NJ", "MD", "DC"}
    pin(
        # USDA's minimum for households of one or two in the 48 states and DC
        # (fns.usda.gov/snap/allotment/cola), above.
        "SNAP pays every eligible household of one or two people at least a "
        "minimum benefit, which in these households' states is ${minimumMonthly} "
        "a month through September 2026 and ${minimumFromOctober} from October.",
        # PolicyBench scores every answer against the PolicyEngine reference
        # (the payload's groundTruth is the committed reference CSV), below.
        # The freeze date is the law cutoff the references follow, as the
        # convention's rule states it; the references themselves were rebuilt
        # on the engine upgrade's date, after it.
        "PolicyBench grades answers against references from PolicyEngine, the "
        "open-source tax and benefit model, and the references follow law "
        f"published before PolicyBench's {_month_day(freeze.group(1))} reference "
        "freeze.",
        f"USDA published the ${{minimumFromOctober}} minimum on "
        f"{_month_day(fy2027.group(1))}, so the references keep "
        "${minimumMonthly} through December and put each household at that "
        "minimum for each month it qualifies: ${referenceAmount} for 2026 for "
        "{fullYearCount:words} households, and ${azReference} for an "
        f"{names[arizona]} resident who qualifies from March.",
    )
    for scenario_id in households:
        for entry in payload["scenarioPredictions"][scenario_id]["snap"].values():
            assert entry["groundTruth"] == references[scenario_id]
            assert entry["scored"] is True

    # The ordinary tests. Every one has gross income above the ordinary gross
    # limit; the ones that pass the gross test anyway have a member the engine
    # treats as elderly or disabled, which exempts them from it, and fail the
    # net income test instead.
    snap_parameters = pathway_meta["snap_parameters"]
    assert len({p["gross_income_limit_fpg"] for p in snap_parameters.values()}) == 1
    snap_gross_limit = snap_parameters["2026-01-01"]["gross_income_limit_fpg"]
    assert (
        "return has_elderly_disabled | (income <= limit)"
        in (rules["meets_snap_gross_income_test"])
    )
    for row in income_group:
        assert float(row["gross_income_fpg_ratio_min"]) > snap_gross_limit
        exempt = row["elderly_or_disabled_months"] == "12"
        assert row["elderly_or_disabled_months"] in {"0", "12"}
        assert row["gross_income_test_months"] == ("12" if exempt else "0")
        for key in ("net_income_test_months", "asset_test_months"):
            assert row[key] in {"0", "12"}

    def failing(key: str) -> set[str]:
        return {row["scenario_id"] for row in income_group if row[key] == "0"}

    fail_gross = failing("gross_income_test_months")
    fail_net = failing("net_income_test_months")
    fail_assets = failing("asset_test_months")
    assert fail_gross == {texas_id}
    assert fail_net == set(households)
    assert fail_assets == {couple_id, arizona}
    exempt_from_gross = set(households) - fail_gross
    assert len(exempt_from_gross) == 4
    sizes = {s: int(by_id[s]["household_size"]) for s in households}
    assert set(sizes.values()) <= {1, 2}
    pin(
        # 7 CFR 273.10(e)(2)(ii)(C): "Except during an initial month, all
        # eligible one-person and two-person households shall receive minimum
        # monthly allotments equal to the minimum benefit". An initial month's
        # prorated allotment can fall below it (273.10(e)(2)(ii)(B)); the
        # references are full-year amounts with no proration, so $0 for the
        # year is the answer for a household that qualifies in no month (the
        # minimum checks above).
        "Each of the {householdCount:words} has one or two people, so an answer "
        "of $0 says the household does not qualify, and that answer could keep "
        "someone who qualifies from applying."
    )
    # The Texas resident with wages and financial assistance.
    texan = _person(scenarios[texas_id], "head")
    assert sizes[texas_id] == 1
    assert texan["employment_income"] > 0
    financial_assistance = texan["financial_assistance"]
    # The Connecticut couple on Social Security disability income, with savings
    # above the asset limit.
    couple = scenarios[couple_id]
    assert sizes[couple_id] == 2 and couple["filing_status"] == "joint"
    assert [p["name"] for p in couple["adults"]] == ["head", "spouse"]
    assert not couple["children"]
    couple_head = _person(couple, "head")
    assert couple_head["social_security_disability"] > 0
    savings = couple_head["bank_account_assets"]
    assert savings > 0 and not _person(couple, "spouse").get("bank_account_assets")
    # The disabled Michigan resident living alone: under 60 and on Social
    # Security disability income, so the engine's elderly or disabled member.
    alone = _person(scenarios[michigan_id], "head")
    assert sizes[michigan_id] == 1
    assert alone["age"] < 60 and alone["social_security_disability"] > 0
    # The surviving spouse in Wisconsin.
    widow = _person(scenarios[wisconsin_id], "head")
    assert sizes[wisconsin_id] == 1 and widow["is_surviving_spouse"] is True
    # The Arizona resident living alone, on Social Security retirement income
    # and a private pension (and $88 of dividends and gains), with savings.
    arizonan = _person(scenarios[arizona], "head")
    assert sizes[arizona] == 1 and arizonan["age"] >= 60
    income_like = re.compile(
        r"income|benefit|pension|social_security|dividend|interest|gain|alimony"
    )
    arizona_income = {
        key: value
        for key, value in arizonan.items()
        if value and income_like.search(key) and isinstance(value, float)
    }
    assert set(arizona_income) == {
        "social_security_retirement",
        "taxable_private_pension_income",
        "non_qualified_dividend_income",
        "non_sch_d_capital_gains",
    }
    assert (
        arizona_income["non_qualified_dividend_income"]
        + arizona_income["non_sch_d_capital_gains"]
        < 100
    )
    arizona_savings = arizonan["bank_account_assets"]
    pin(
        "All {householdCount:words} households have gross income above "
        "{snapGrossLimit}% of the guideline, but SNAP exempts households with an "
        "elderly or disabled member from its ordinary gross income test.",
        "Four of the {householdCount:words} have such a member: a "
        f"{names[couple_id]} couple on Social Security disability income, a "
        f"disabled {names[michigan_id]} resident living alone, an "
        f"{{wiAge}}-year-old surviving spouse in {names[wisconsin_id]}, and an "
        f"{{azAge}}-year-old {names[arizona]} resident on Social Security and a "
        "pension.",
        f"The fifth, a {{txAge}}-year-old {names[texas_id]} resident with wages "
        "and ${financialAssistance} of financial assistance, fails that test.",
        "The four exempt households fail SNAP's ordinary net income test "
        f"instead, and the {names[couple_id]} couple and the {names[arizona]} "
        "resident also hold ${ctSavings} and ${azSavings} in savings, above "
        "SNAP's asset limit.",
    )
    # "an {wiAge}-year-old" and "an {azAge}-year-old" read as "an 85-" and
    # "an 80-".
    assert str(widow["age"]).startswith("8") and str(arizonan["age"]).startswith("8")

    # The Michigan resident's premiums. The tests above follow the engine's
    # reading of the listed employer-sponsored insurance premiums, which it
    # documents as employer-paid. The recomputation also moves them into the
    # resident's own premiums, which SNAP counts as a medical expense of a
    # disabled member: among the five, only the Michigan resident lists any,
    # and then passes the net income test all year, qualifies through the
    # ordinary tests, and gets the same minimum.
    premiums = pathway_meta["employer_premiums_paid_by_household"]
    assert "employer-paid" in premiums["engine_documentation"]
    with_premiums = {
        scenario_id
        for scenario_id in households
        for person in [
            *scenarios[scenario_id]["adults"],
            *scenarios[scenario_id]["children"],
        ]
        if person["inputs"].get("employer_sponsored_insurance_premiums")
    }
    assert with_premiums == {michigan_id}
    assert set(premiums["households"]) & set(households) == {michigan_id}
    paid = premiums["households"][michigan_id]
    assert all(
        with_paid < as_listed
        for with_paid, as_listed in zip(
            (float(v) for v in paid["monthly_net_income_premiums_paid"].split()),
            (float(v) for v in paid["monthly_net_income"].split()),
            strict=True,
        )
    )
    assert paid["net_income_test_months_premiums_paid"] == 12
    assert by_id[michigan_id]["net_income_test_months"] == "0"
    assert set(paid["pathway_by_month_premiums_paid"].split()) == {"ordinary"}
    assert [float(v) for v in paid["monthly_snap_premiums_paid"].split()] == [
        minimum
    ] * 12
    for prompt in payload["scenarios"][michigan_id]["prompt"].values():
        assert "- employer sponsored insurance premiums: $" in _household_block(prompt)
    # GPT-5.5's exact answer for the Michigan resident takes that route: it
    # deducts medical premiums, passes the net income test, and applies the
    # minimum, with no word of categorical eligibility.
    predictions = payload["scenarioPredictions"]

    def explanation(scenario_id: str, model: str) -> str:
        return predictions[scenario_id]["snap"][model].get("explanation") or ""

    bbce_regex = re.compile(regexes["bbce"], re.IGNORECASE)
    gpt55 = explanation(michigan_id, "gpt-5.5")
    assert predictions[michigan_id]["snap"]["gpt-5.5"]["exact"] == 100
    assert (
        "allowable medical premiums/expenses reduce net income below the "
        "net-income limit" in gpt55
    )
    assert "minimum SNAP allotment of $24 per month" in gpt55
    assert not bbce_regex.search(gpt55)
    pin(
        f"The {names[michigan_id]} resident's prompt lists employer-sponsored "
        "insurance premiums, and PolicyEngine treats the employer as paying them.",
        "Had the resident paid them, SNAP would count them as a medical expense, "
        "and the household would pass the net income test and get the same "
        "minimum without BBCE.",
        f"GPT-5.5 gets the {names[michigan_id]} resident's amount right by that "
        "route: its explanation deducts medical premiums, puts net income below "
        "the net income limit, and applies the minimum.",
    )

    # The engine's BBCE rule, read from policyengine-us 2.15.17's code:
    # categorical eligibility through SSI, TANF cash, or the TANF-funded
    # non-cash benefit, for which a household qualifies on the state's income
    # and asset tests alone; nothing in it reads receipt of the benefit.
    bbce = pathway_meta["bbce_parameters"]
    assert bbce["snap_categorical_eligibility_programs"] == [
        "ssi",
        "is_tanf_non_cash_eligible",
        "tanf",
    ]
    categorical = rules["meets_snap_categorical_eligibility"]
    assert "parameters(period).gov.usda.snap.categorical_eligibility" in categorical
    assert "(add(spm_unit, period, spm_level_programs) > 0)" in categorical
    assert re.findall(r'spm_unit\("(\w+)"', rules["is_tanf_non_cash_eligible"]) == [
        "meets_tanf_non_cash_gross_income_test",
        "meets_tanf_non_cash_net_income_test",
        "meets_tanf_non_cash_asset_test",
    ]
    assert "return gross & net & asset" in rules["is_tanf_non_cash_eligible"]
    assert (
        "(normal_eligibility | categorical_eligibility)" in (rules["is_snap_eligible"])
    )
    # The three tests read income, assets, the state's limits and whether a
    # member is elderly or disabled; none of them, nor the gross limit and
    # the status they read, reads receipt of the benefit or an authorization.
    read_by_tests = set()
    for name in (
        "meets_tanf_non_cash_gross_income_test",
        "meets_tanf_non_cash_net_income_test",
        "meets_tanf_non_cash_asset_test",
        "tanf_non_cash_gross_income_limit",
        "is_tanf_non_cash_hheod",
    ):
        read_by_tests |= set(
            re.findall(r'spm_unit(?:\.household)?\(\s*"(\w+)"', rules[name])
        )
    assert read_by_tests == {
        "has_all_usda_elderly_disabled",
        "has_snap_elderly_disabled_member",
        "household_vehicles_owned",
        "household_vehicles_value",
        "is_tanf_non_cash_hheod",
        "snap_assets",
        "snap_dependent_care_deduction",
        "snap_earned_income",
        "snap_gross_test_income",
        "snap_net_income",
        "state_code_str",
        "tanf_non_cash_fpg",
        "tanf_non_cash_gross_income_limit",
    }
    # The rule's other routes read receipt of TANF cash and SSI, which no
    # household here lists (below).
    assert re.findall(r'(?:spm_unit|person)\(\s*"(\w+)"', categorical) == [
        "ssi",
        "receives_ssi",
        "receives_tanf",
    ]
    # The states' limits for the non-cash benefit through 2026: Arizona's
    # rises on March 1; no other changes.
    state_rules = bbce["state_tanf_non_cash"]
    assert list(state_rules) == ["2026-01-01", "2026-03-01", "2026-10-01"]
    income_states = sorted(set(states.values()))
    for instant, by_state in state_rules.items():
        for state in income_states:
            rule = by_state[state]
            assert (
                rule["gross_income_limit_fpg"]
                == rule["gross_income_limit_fpg_elderly_disabled"]
            )
            assert not rule["net_income_test_applies"]
            assert not rule["net_income_test_applies_elderly_disabled"]
            assert (rule["asset_limit"] is None) == (state != "TX")
        for state in set(by_state) - {"AZ"}:
            assert by_state[state] == state_rules["2026-01-01"][state]
    march = state_rules["2026-03-01"]
    high = max(march[s]["gross_income_limit_fpg"] for s in income_states)
    high_states = sorted(
        s for s in income_states if march[s]["gross_income_limit_fpg"] == high
    )
    assert high_states == ["AZ", "CT", "MI", "WI"]
    assert state_rules["2026-10-01"]["AZ"] == march["AZ"]
    az_before = state_rules["2026-01-01"]["AZ"]["gross_income_limit_fpg"]
    texas_limit = march["TX"]["gross_income_limit_fpg"]
    assert snap_gross_limit < texas_limit < az_before < high
    high_limit = round(100 * high)
    # Each household is eligible for the non-cash benefit in each month it
    # qualifies, under its state's gross limit then and over it otherwise,
    # and receives neither TANF cash nor SSI.
    tanf_references = _snap_output_references("tanf", references_path)
    ssi_references = _snap_output_references("ssi", references_path)
    for row in income_group:
        scenario_id = row["scenario_id"]
        months = eligible_months[scenario_id]
        assert row["tanf_non_cash_eligible_months"] == str(len(months))
        assert row["tanf_non_cash_gross_test_by_month"].split() == [
            "1" if i in months else "0" for i in range(12)
        ]
        assert float(row["tanf"]) == 0
        assert tanf_references[scenario_id] == 0
        assert ssi_references[scenario_id] == 0
        assert not re.search(
            r'"receives_(?:tanf|ssi)"', json.dumps(scenarios[scenario_id])
        )
        assert set(row["pathway_by_month"].split()) - {"ineligible"} <= {
            "categorical_income",
            "categorical_both",
        }
    # The Arizona resident's gross income falls between the old and the new
    # limit in every month, so the non-cash test fails in January and
    # February and holds from March.
    az_row = by_id[arizona]
    assert (
        az_before
        < float(az_row["tanf_non_cash_gross_ratio_min"])
        <= float(az_row["tanf_non_cash_gross_ratio_max"])
        < high
    )
    high_names = [STATE_NAMES[s] for s in high_states]
    texas = names[texas_id]
    assert set(income_states) - set(high_states) == {states[texas_id]}
    pin(
        "Each household qualifies only through broad-based categorical "
        "eligibility (BBCE).",
        # The ordinary tests BBCE loosens: the gross income limit (above), net
        # income after the allowed deductions, which include the excess
        # shelter deduction, and the asset test (the pathway columns count
        # all three).
        "Ordinarily, SNAP tests a household's gross income against "
        "{snapGrossLimit}% of the federal poverty guideline, its net income "
        "after deductions for costs such as housing, and its savings.",
        # The rule, 7 CFR 273.2(j)(2)(ii): every member "receive[s] or [is]
        # authorized to receive" the TANF-funded non-cash service.
        "Under BBCE, a state extends SNAP to households that receive a non-cash "
        "benefit funded by Temporary Assistance for Needy Families (TANF), or "
        "that the state has authorized to receive one.",
        f"{', '.join(high_names[:-1])}, and {high_names[-1]} open that benefit, "
        "and with it SNAP, to households with gross income up to "
        "{bbceGrossLimitHigh}% of the guideline, and "
        f"{texas} opens it to those up to {{bbceGrossLimitTx}}%.",
        f"{names[arizona]} raised its limit from {{azLimitBefore}}% to "
        "{bbceGrossLimitHigh}% starting with benefit month March 2026.",
        "None of these states tests net income for the non-cash benefit, and "
        f"only {texas} keeps an asset limit for it.",
        "Each household's gross income is under its state's BBCE limit, the "
        f"{names[arizona]} resident's from March.",
        # The single formula and the contributions above the maximum (above).
        "BBCE leaves SNAP's benefit formula in place, and at these incomes the "
        "formula pays nothing, so each household gets the minimum.",
    )
    # Arizona's raise, as the reference upgrade records it.
    az_change = next(
        c
        for c in upgrade["changed"]
        if (c["scenario_id"], c["variable"]) == (arizona, "snap")
    )
    az_limits = re.search(
        r"from (\d+)% to (\d+)% of poverty from benefit month 03/2026",
        az_change["basis"],
    )
    assert az_limits is not None
    assert (int(az_limits.group(1)), int(az_limits.group(2))) == (
        round(100 * az_before),
        high_limit,
    )
    assert az_change["regenerated"] == references[arizona]

    # The households held back by savings: they pass both income tests all
    # year, fail the asset test, qualify through BBCE, and get a benefit. Their
    # states drop the asset test for the non-cash benefit.
    held_back = [by_id[scenario_id] for scenario_id in savings_households]
    for row in held_back:
        assert row["gross_income_test_months"] == row["net_income_test_months"] == "12"
        assert row["asset_test_months"] == "0"
        assert row["tanf_non_cash_eligible_months"] == "12"
        assert float(row["snap_recomputed"]) > 0
        for by_state in state_rules.values():
            assert by_state[row["state"]]["asset_limit"] is None
        people = scenarios[row["scenario_id"]]["adults"]
        assert sum(p["inputs"].get("bank_account_assets", 0) for p in people) > 0
    asset_states = [STATE_NAMES[row["state"]] for row in held_back]
    pin(
        "PolicyBench also asks models about households in "
        f"{', '.join(asset_states[:-1])}, and {asset_states[-1]} that pass "
        "SNAP's income tests but hold savings above its asset limit, which BBCE "
        "removes in those states."
    )
    # One of them, in Pennsylvania, has its SNAP output excluded for an engine
    # defect not fixed upstream: the engine grants the heat-and-eat standard
    # utility allowance, which a 2025 law (P.L. 119-21) narrowed. Its corrected
    # value and the engine's are both above $0, so it qualifies either way;
    # the upgrade's recheck finds the defect still in 2.15.17.
    excluded_savings = [s for s in savings_households if s in snap_exclusions]
    assert excluded_savings == ["scenario_080"]
    pennsylvania = snap_exclusions["scenario_080"]
    assert by_id["scenario_080"]["state"] == "PA"
    assert by_id["scenario_080"]["snap_scored"] == "False"
    assert pennsylvania["reason_code"] == "reference_engine_defect"
    assert pennsylvania["root_cause"] == "r30_snap_heat_and_eat_sua"
    assert "heat-and-eat standard utility allowance" in pennsylvania["defect"]
    law_year = re.search(
        r"P\.L\. 119-21 sec\. \d+\(a\) \(approved (\d{4})-", pennsylvania["law"]
    )
    assert law_year is not None
    assert pennsylvania["frozen_value"] > 0 and pennsylvania["alternative_value"] > 0
    assert "excluded either way" in pennsylvania["note"]
    recheck = next(
        r
        for r in upgrade["excluded_outputs_rechecked"]
        if (r["scenario_id"], r["variable"]) == ("scenario_080", "snap")
    )
    assert recheck["value_on_2_15_17"] > 0
    assert "The r30 defect is unfixed in 2.15.17" in recheck["reason"]
    assert all(
        row["scored"] is False
        for row in asset_rows
        if row["scenario_id"] == "scenario_080"
    )
    pin(
        f"PolicyBench does not score the {STATE_NAMES['PA']} household's SNAP "
        "amount, because PolicyEngine grants it the heat-and-eat utility "
        f"allowance, which a {law_year.group(1)} law narrowed.",
        "With or without that allowance, the household qualifies for a benefit.",
    )

    # The answers. Answers that did not parse carry no value and no
    # explanation; every other answer has an explanation.
    board = [row for row in payload["modelStats"] if row["condition"] == "no_tools"]
    by_model = {row["model"]: row for row in board}
    display = {model: MODEL_DISPLAY_NAMES[model] for model in by_model}
    assert len(rows) == len(board) * len(households)
    assert len(asset_rows) == len(board) * len(savings_households)
    missing = [row for row in rows if row["prediction"] == ""]
    asset_missing = [row for row in asset_rows if row["prediction"] == ""]
    for row in [*missing, *asset_missing]:
        entry = predictions[row["scenario_id"]]["snap"][row["model"]]
        assert entry["parsed"] is False and not entry.get("explanation")
    returned = [row for row in rows if row["prediction"] != ""]
    asset_returned = [row for row in asset_rows if row["prediction"] != ""]
    explained = [
        row for row in rows if explanation(row["scenario_id"], row["model"]).strip()
    ]
    asset_explained = [
        row
        for row in asset_rows
        if explanation(row["scenario_id"], row["model"]).strip()
    ]
    # Every answer a model gives comes with an explanation, so the shares
    # above $0 and the explanation counts share their denominators.
    assert len(returned) == len(explained)
    assert len(asset_returned) == len(asset_explained)
    zero_rows = [row for row in rows if row["prediction"] == 0.0]
    above_zero = [row for row in rows if row["prediction"] not in ("", 0.0)]
    assert all(row["prediction"] > 0 for row in above_zero)
    # Most models answer $0 for each of the five, and most miss the amount.
    for scenario_id in households:
        zeros = sum(row["scenario_id"] == scenario_id for row in zero_rows)
        assert 2 * zeros > len(board), scenario_id
        hits_here = sum(
            row["within_1_dollar"] for row in rows if row["scenario_id"] == scenario_id
        )
        assert 2 * hits_here < len(board), scenario_id
    # The title holds for all five: each qualifies only through BBCE, with
    # gross income above SNAP's ordinary gross limit and under its state's
    # BBCE limit, which is higher.
    assert note["title"] == (
        "Most models answer $0 for households that qualify for SNAP under their "
        "states' higher income limits"
    )
    pin(
        "For each of {householdCount:words} households that qualify for SNAP "
        "food benefits, most of the {nModels} models on PolicyBench answer $0.",
        "Of the {answers} answers PolicyBench requests for these households, "
        "{zeroAnswers} come to $0 and {hits:words} match the reference.",
    )
    hits_by_model = {
        model: sum(row["within_1_dollar"] for row in rows if row["model"] == model)
        for model in by_model
    }

    # Most models answer above $0 for each household held back by savings.
    asset_above_zero = [row for row in asset_rows if row["prediction"] not in ("", 0.0)]
    assert all(row["prediction"] > 0 for row in asset_above_zero)
    for scenario_id in savings_households:
        above = sum(row["scenario_id"] == scenario_id for row in asset_above_zero)
        assert 2 * above > len(board), scenario_id
    pin(
        "When savings rather than income hold a household back, most models "
        "answer above $0.",
        "Of the answers models give for those {assetOnlyCount:words} households, "
        "{assetOnlyAbove0Share}% come in above $0, against {incomeAbove0Share}% "
        "for the {householdCount:words} held back by income.",
    )
    # The models that answer above $0 on every household held back by savings
    # and $0 on each household held back by income, among them the two
    # highest-ranked, which the prose names with their ranks.
    split_models = sorted(
        model
        for model in by_model
        if all(
            row["prediction"] not in ("", 0.0)
            for row in asset_rows
            if row["model"] == model
        )
        and all(row["prediction"] == 0.0 for row in rows if row["model"] == model)
    )
    named_split = ["gpt-5.6-sol", "gpt-6-luna"]
    assert set(named_split) <= set(split_models)
    split_ranks = sorted(_rank(by_model[m]["exact"], board) for m in split_models)
    assert [_rank(by_model[m]["exact"], board) for m in named_split] == split_ranks[:2]
    pin(
        "Of the {nModels} models, {splitModels} answer above $0 for each household "
        "held back by savings and $0 for each of the {householdCount:words} held "
        f"back by income, among them {display['gpt-5.6-sol']} and "
        f"{display['gpt-6-luna']}, #{{sol56Rank}} and #{{lunaRank}} on PolicyBench."
    )

    # The explanations. Every prompt asks for an explanation of each answer.
    # The BBCE pattern counts the name, "categorical eligibility", spaced or
    # hyphenated ("categorical-eligibility ceiling"), and a state's "expanded
    # categorical" limit; the net income pattern counts a net income limit or
    # test (or its 100%-of-poverty level), which none of the five states
    # applies under BBCE (above).
    for scenario in payload["scenarios"].values():
        for prompt in scenario["prompt"].values():
            assert (
                "a numeric `value` and a non-empty, specific, concise "
                "`explanation`" in prompt
            )
    assert regexes["netLimit"].startswith(r"\bnet[- ](?:income[- ])?(?:limit|test|")
    # Whatever joins the words, every explanation that calls a household
    # categorically eligible, or cites an expanded categorical limit, is
    # counted as mentioning BBCE.
    any_joiner = re.compile(
        r"categorical(?:ly)?\W*eligib|expanded\W+categorical", re.IGNORECASE
    )
    for row in [*rows, *asset_rows]:
        text_here = explanation(row["scenario_id"], row["model"])
        if any_joiner.search(text_here):
            assert bbce_regex.search(text_here), (row["model"], row["scenario_id"])
    income_mentions = [row for row in rows if row["mentions_categorical_eligibility"]]
    income_mention_zeros = [row for row in income_mentions if row["prediction"] == 0.0]
    asset_mentions = [
        row for row in asset_rows if row["mentions_categorical_eligibility"]
    ]
    # The households held back by income get the smaller share.
    assert len(asset_mentions) * len(explained) > len(income_mentions) * len(
        asset_explained
    )
    # The 13 explanations that mention BBCE and end at $0, read one by one:
    # those that write the household's income exceeds its state's BBCE limit,
    # with the words that say so, and the two that apply BBCE and leave out
    # the minimum.
    over_limit = {
        ("gemini-3.5-flash", arizona): (
            "exceeds the Broad-Based Categorical Eligibility threshold (185% of "
            "the Federal Poverty Level) for Arizona"
        ),
        ("gemini-3.8-flash", arizona): (
            "exceeds Arizona's broad-based categorical eligibility limit (185% FPL)"
        ),
        ("gpt-6-astra", arizona): (
            "Income exceeds Arizona's categorical-eligibility income limit"
        ),
        ("gpt-6.1-sol", arizona): (
            "Income exceeds Arizona's expanded categorical eligibility limit"
        ),
        (
            "claude-opus-4.7",
            texas_id,
        ): "TX uses BBCE at 165% FPL (~$2,072) — still over",
        ("grok-4.6", texas_id): (
            "well above both the 130 percent FPL regular gross-income test and "
            "Texas BBCE 165 percent FPL limit"
        ),
    }
    formula_only = {
        ("gemini-3-flash-preview", couple_id): (
            "passes the 200% FPL Broad-Based Categorical Eligibility threshold for "
            "Connecticut, but the benefit calculation (Max Allotment minus 30% of "
            "Net Income) results in zero"
        ),
        ("gemini-3.1-pro-preview", couple_id): (
            "Although the household meets categorical eligibility criteria, 30% of "
            "their net countable income exceeds the maximum SNAP benefit"
        ),
    }
    net_regex = re.compile(regexes["netLimit"], re.IGNORECASE)
    with_net = {
        (row["model"], row["scenario_id"])
        for row in income_mention_zeros
        if row["mentions_net_income_limit"]
    }
    for key, words in {**over_limit, **formula_only}.items():
        assert words in explanation(key[1], key[0]), key
    for key in formula_only:
        assert "minimum" not in explanation(key[1], key[0]).lower()
    zero_keys = {(row["model"], row["scenario_id"]) for row in income_mention_zeros}
    assert set(over_limit) | set(formula_only) <= zero_keys
    # Each of the 13 cites a net income limit, the BBCE limit, or the formula;
    # one Texas explanation cites both a net income limit and the BBCE limit,
    # so the three groups the prose counts (over the limit, a net income
    # limit only, the formula only) are disjoint and add up to the 13.
    assert zero_keys == with_net | set(over_limit) | set(formula_only)
    assert with_net & set(over_limit) == {("claude-opus-4.7", texas_id)}
    assert not with_net & set(formula_only)
    assert not set(over_limit) & set(formula_only)
    net_only = with_net - set(over_limit)
    assert len(over_limit) + len(net_only) + len(formula_only) == len(zero_keys)
    # PolicyEngine puts both under their state's limits (the non-cash gross
    # test above): Texas all year, Arizona from March.
    assert {s for _, s in over_limit} == {arizona, texas_id}
    assert by_id[texas_id]["tanf_non_cash_gross_test_months"] == "12"
    pin(
        "PolicyBench asks each model to explain every answer, and the "
        "explanations mention BBCE less often for the households held back by "
        "income.",
        "For the households held back by savings, {assetOnlyBbceMentions} of "
        "{assetOnlyExplanations} explanations mention BBCE, by name or as "
        "categorical eligibility, and {assetOnlyBbceAssets} of those also "
        "mention assets.",
        "For the {householdCount:words} held back by income, {incomeBbceMentions} "
        "of {explanations} explanations mention BBCE, and {incomeBbceZeros} of "
        "those still end at $0.",
        "Of those {incomeBbceZeros}, {incomeBbceZeroOverLimit:words} write that "
        "the household's income exceeds its state's BBCE limit: "
        f"{{overLimitAz:words}} for the {names[arizona]} resident and "
        f"{{overLimitTx:words}} for the {texas} resident.",
        "PolicyEngine puts both households under their states' limits, the "
        f"{names[arizona]} resident from March.",
        # "Another": the net-only group, disjoint from the over-limit group
        # (above). No state here tests net income under BBCE (above).
        "Another {netLimitOnly:words} cite a net income limit or test, though "
        "none of these households' states applies one under BBCE.",
        f"The last {{formulaOnly:words}}, from "
        f"{display['gemini-3-flash-preview']} and "
        f"{display['gemini-3.1-pro-preview']}, write that the {names[couple_id]} "
        "couple meets BBCE, then answer $0 because the benefit formula pays "
        "nothing, and neither applies the minimum.",
    )
    # The explanations that mention BBCE and answer above $0: those that match
    # the reference, and those that apply the minimum at twelve times one
    # monthly amount below this year's, $23, which every one of them writes
    # (or its $276 a year) beside the word minimum. $23 is the minimum the
    # engine gives for FY2024 and FY2025, through September 2025.
    above_mentions = [
        row for row in income_mentions if row["prediction"] not in ("", 0.0)
    ]
    assert len(income_mention_zeros) + len(above_mentions) == len(income_mentions)
    income_hits = [row for row in above_mentions if row["within_1_dollar"]]
    stale = [row for row in above_mentions if row["prediction"] < reference_amount]
    assert not any(row["within_1_dollar"] for row in stale)
    (stale_annual,) = {row["prediction"] for row in stale}
    fy2025_minimum = stale_annual / 12
    assert fy2025_minimum.is_integer() and fy2025_minimum < minimum
    fy2025_minimum = int(fy2025_minimum)
    for row in stale:
        stale_text = explanation(row["scenario_id"], row["model"])
        assert "minimum" in stale_text.lower(), row["model"]
        assert (
            f"${fy2025_minimum}" in stale_text or f"${int(stale_annual)}" in stale_text
        ), row["model"]
    if engine_minimums is not None:
        assert engine_minimums[2024] == engine_minimums[2025] == fy2025_minimum
    pin(
        "Of the {incomeBbceAbove0} that mention BBCE and answer above $0, "
        "{incomeBbceHits:words} match the reference, and {staleMinimum:words} "
        "apply the minimum at its amount through September 2025, "
        "${fy2025Minimum} a month, and answer ${fy2025MinimumAnnual}."
    )

    # GPT-6 Astra gets the most, each hit citing its state's high gross limit
    # for categorical eligibility, and answers $0 for the household that
    # fails the ordinary gross test and for the Arizona resident.
    best = max(hits_by_model.values())
    assert [m for m, h in hits_by_model.items() if h == best] == ["gpt-6-astra"]
    astra_hits = sorted(
        s for s in households if predictions[s]["snap"]["gpt-6-astra"]["exact"] == 100
    )
    assert len(astra_hits) == best
    for scenario_id in astra_hits:
        assert states[scenario_id] in high_states
        assert (
            f"{STATE_NAMES[states[scenario_id]]}'s {high_limit}%-of-poverty categorical"
        ) in explanation(scenario_id, "gpt-6-astra")
        assert bbce_regex.search(explanation(scenario_id, "gpt-6-astra"))
    astra_zeros = {
        s
        for s in households
        if predictions[s]["snap"]["gpt-6-astra"]["prediction"] == 0
    }
    assert astra_zeros == fail_gross | {arizona}
    assert set(astra_hits) | astra_zeros == set(households)
    # GPT-6.1 Sol: the Michigan and Wisconsin households, each citing the
    # state's categorical limit.
    sol61_hits = sorted(
        s for s in households if predictions[s]["snap"]["gpt-6.1-sol"]["exact"] == 100
    )
    assert sol61_hits == [michigan_id, wisconsin_id]
    assert "below Michigan's expanded categorical gross-income limit" in explanation(
        michigan_id, "gpt-6.1-sol"
    )
    assert (
        f"below Wisconsin's {high_limit}%-of-poverty categorical-eligibility limit"
        in explanation(wisconsin_id, "gpt-6.1-sol")
    )
    pin(
        f"{display['gpt-6-astra']} gets {{astraHits:words}} of the "
        "{householdCount:words} households right, more than any other model, and "
        "cites the state's BBCE limit of {bbceGrossLimitHigh}% of the guideline "
        "each time.",
        f"It answers $0 for the {texas} resident, the one household that fails "
        f"SNAP's ordinary gross income test, and for the {names[arizona]} resident.",
        f"{display['gpt-6.1-sol']} gets {{sol61Hits:words}} right, the "
        f"{names[michigan_id]} and {names[wisconsin_id]} households, citing each "
        "state's categorical eligibility limit.",
    )

    # Claude Opus 5.5: the minimum for the Wisconsin surviving spouse, citing
    # Wisconsin's BBCE and its gross limit; $0 for the Connecticut couple,
    # the Michigan resident and the Arizona resident, citing the net income
    # test, which their states drop under BBCE.
    opus_name = display["claude-opus-5.5"]
    opus = {
        s: predictions[s]["snap"]["claude-opus-5.5"]["prediction"] for s in households
    }
    assert opus[wisconsin_id] == reference_amount
    opus_108 = explanation(wisconsin_id, "claude-opus-5.5")
    assert "Wisconsin's broad-based categorical eligibility" in opus_108
    assert f"under {high_limit}% FPL" in opus_108
    for scenario_id in (couple_id, michigan_id, arizona):
        assert opus[scenario_id] == 0
        opus_text = explanation(scenario_id, "claude-opus-5.5")
        assert net_regex.search(opus_text) and "net income" in opus_text
        assert not bbce_regex.search(opus_text)
        for by_state in state_rules.values():
            assert by_state[states[scenario_id]]["net_income_test_applies"] is False
    pin(
        f"{opus_name} answers ${{opusOn108}} for the {names[wisconsin_id]} "
        f"surviving spouse, citing {names[wisconsin_id]}'s BBCE and its "
        "{bbceGrossLimitHigh}% limit.",
        f"For the {names[couple_id]} couple, the disabled {names[michigan_id]} "
        f"resident, and the {names[arizona]} resident, it answers $0, citing "
        "SNAP's ordinary net income test, which BBCE removes in all three states.",
    )

    # GPT-6 Sol leads the board; its answers and its BBCE mentions across the
    # whole board, one explanation for each household.
    sol6_name = display["gpt-6-sol"]
    assert _rank(by_model["gpt-6-sol"]["exact"], board) == 1
    sol6 = {s: predictions[s]["snap"]["gpt-6-sol"]["prediction"] for s in households}
    assert [s for s, v in sol6.items() if v != 0] == [texas_id]
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
        "{sol6ZeroCount:words} of the {householdCount:words} and mentions BBCE in "
        "{sol6BbceMentions:words} of its SNAP explanations for PolicyBench's "
        "{boardHouseholds} households."
    )

    # The Texas resident: three models compute an ordinary benefit from wages
    # alone; the engine counts the financial assistance (and not the
    # educational assistance) as income, which takes the household above the
    # ordinary gross and net limits and leaves BBCE as its only route.
    sonnet_name = display["claude-sonnet-5.5"]
    wages_only = ("gpt-6-sol", "claude-opus-5.5", "claude-sonnet-5.5")
    texas_answers = {
        m: predictions[texas_id]["snap"][m]["prediction"] for m in wages_only
    }
    assert texas_answers["claude-opus-5.5"] == texas_answers["claude-sonnet-5.5"]
    for model in wages_only:
        assert texas_answers[model] > 0
        assert abs(texas_answers[model] - reference_amount) > 1
        assert not any(
            row["within_1_dollar"]
            for row in rows
            if (row["model"], row["scenario_id"]) == (model, texas_id)
        )
    assert "30% of monthly wages after the 20% earned-income" in explanation(
        texas_id, "gpt-6-sol"
    )
    assert "financial and educational assistance are not counted" in explanation(
        texas_id, "claude-opus-5.5"
    )
    assert "I counted wages only and treated the assistance amounts as excluded" in (
        explanation(texas_id, "claude-sonnet-5.5")
    )
    for parameters in snap_parameters.values():
        sources = parameters["unearned_income_sources"]
        assert "financial_assistance" in sources
        assert "educational_assistance" not in sources
    row_030 = by_id[texas_id]
    ratio_030 = float(row_030["gross_income_fpg_ratio_min"])
    wages_030 = texan["employment_income"]
    wages_only_ratio = ratio_030 * wages_030 / (wages_030 + financial_assistance)
    assert wages_only_ratio < snap_gross_limit < ratio_030
    assert texas_id in fail_gross & fail_net
    # The prompt labels the money only "financial assistance".
    for prompt in payload["scenarios"][texas_id]["prompt"].values():
        lines = [
            line
            for line in _household_block(prompt).splitlines()
            if "financial" in line.lower()
        ]
        assert lines == [f"- financial assistance: ${financial_assistance:,.0f}"]
    texas_paragraph = next(p for p in note["paragraphs"] if "labels that money" in p)
    assert re.findall(r'"([^"]+)"', texas_paragraph) == ["financial assistance"]
    pin(
        f"{sol6_name}, {opus_name}, and {sonnet_name} miss the {texas} resident's "
        "amount because they count less income than PolicyEngine does.",
        f"{sol6_name} answers ${{sol6On030}}, and {opus_name} and {sonnet_name} "
        "each answer ${opusOn030}.",
        "All three compute an ordinary benefit from wages alone.",
        "PolicyEngine also counts the ${financialAssistance} of financial "
        "assistance as income, which puts the household above SNAP's ordinary "
        "limits and leaves BBCE as its only route.",
        # SNAP excludes educational assistance (7 CFR 273.9(c)(3)); the engine's
        # unearned income sources count financial assistance and leave
        # educational assistance out (above).
        'The prompt labels that money only "financial assistance", without '
        "naming its source, and SNAP counts some kinds of assistance as income "
        "but excludes others, such as educational assistance.",
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
    for quote, sentence in zip(quotes, PREFACE_SENTENCES, strict=True):
        assert quote.rstrip(".,").lower() in sentence.lower()
    pin(
        # Each prompt's only TANF line asks for the TANF amount (above).
        "No prompt mentions the non-cash benefit, and each mentions TANF only "
        "to ask for the household's TANF amount.",
        "Every prompt tells the model to treat any unlisted household fact or "
        'status "as false", to assume "program take-up when required", and not '
        'to infer unlisted "benefit receipt".',
        # The quotations follow the preface's order (above). The sentence says
        # what the rules tell a model, not what models do: only one
        # explanation of a $0 answer mentions TANF (below).
        "The rules on unlisted statuses and benefit receipt tell a model the "
        # "Can": the preface assumes take-up "when required", and whether that
        # reaches a non-cash benefit the prompt never names is a reading.
        "household lacks the non-cash benefit, while the take-up rule can tell "
        "it the household takes that benefit up.",
        # The engine's code reads eligibility for the non-cash benefit, from
        # the state's income and asset tests, and no receipt (above).
        "PolicyEngine applies BBCE to any household eligible for the non-cash "
        "benefit, without checking whether the household receives it or holds "
        "the state's authorization to receive it.",
        # Each fails the net income test, one also the gross, and none
        # receives TANF cash or SSI (above).
        "A model that requires receipt or authorization falls back on SNAP's "
        "ordinary tests, and each of the {householdCount:words} fails at least "
        "one.",
    )
    # The one $0 explanation that mentions TANF says Texas has no BBCE, and
    # later that the household receives neither TANF nor SSI.
    tanf_regex = re.compile(regexes["tanf"], re.IGNORECASE)
    zero_tanf = [
        (row["model"], row["scenario_id"])
        for row in zero_rows
        if tanf_regex.search(explanation(row["scenario_id"], row["model"]))
    ]
    assert zero_tanf == [("claude-sonnet-4.6", texas_id)]
    zero_tanf_model, zero_tanf_household = zero_tanf[0]
    sonnet46 = explanation(zero_tanf_household, zero_tanf_model)
    assert f"{texas} does NOT have broad-based categorical eligibility (BBCE)" in (
        sonnet46
    )
    assert f"{texas} not having BBCE, the household is ineligible" in sonnet46
    assert (
        "households receiving TANF/SSI" in sonnet46 and "receives neither" in sonnet46
    )
    pin(
        "Among the explanations for the {zeroAnswers} answers of $0, TANF "
        f"appears in {{zeroTanfMentions:words}}: {display[zero_tanf_model]} "
        f"writes that {texas} has no BBCE and that the "
        f"{names[zero_tanf_household]} resident receives neither TANF nor "
        "Supplemental Security Income."
    )

    # The Arizona resident: every model answers $0. Exactly three models give
    # Arizona's limit as the one before March, two of them (above) as its
    # BBCE limit and one as its gross income limit, in whatever form they
    # write the percentage.
    assert all(predictions[arizona]["snap"][m]["prediction"] == 0 for m in by_model)
    before_limit = re.compile(
        rf"(?<![\d.]){round(100 * az_before)}(?:\.0+)?\s*(?:%|percent)",
        re.IGNORECASE,
    )
    cites_before = sorted(
        m for m in by_model if before_limit.search(explanation(arizona, m))
    )
    assert cites_before == [
        "gemini-3-flash-preview",
        "gemini-3.5-flash",
        "gemini-3.8-flash",
    ]
    for model in ("gemini-3.5-flash", "gemini-3.8-flash"):
        assert before_limit.search(over_limit[(model, arizona)])
    assert (
        "exceeds Arizona's gross income limit for a one-person household, which "
        "is 185% of the Federal Poverty Level"
    ) in explanation(arizona, "gemini-3-flash-preview")
    assert "encoded upstream after 1.755.4" in az_change["basis"]
    arizona_over_models = {m for m, s in over_limit if s == arizona}
    assert arizona_over_models == {
        "gpt-6-astra",
        "gpt-6.1-sol",
        "gemini-3.5-flash",
        "gemini-3.8-flash",
    }
    assert arizona_over_models & set(cites_before) == {
        "gemini-3.5-flash",
        "gemini-3.8-flash",
    }
    assert set(cites_before) - arizona_over_models == {"gemini-3-flash-preview"}
    arizona_over_names = [
        display[m]
        for m in (
            "gpt-6-astra",
            "gpt-6.1-sol",
            "gemini-3.5-flash",
            "gemini-3.8-flash",
        )
    ]
    pin(
        f"All {{nModels}} models answer $0 for the {names[arizona]} resident, "
        f"whose gross income falls between {names[arizona]}'s old and new BBCE "
        "limits.",
        # The references come from the upgrade's engine, which encodes the
        # raise (the upgrade's record of the Arizona change, above).
        "PolicyBench's references use policyengine-us {engineVersion}, which "
        "encodes the raise.",
        f"{', '.join(arizona_over_names[:-1])}, and {arizona_over_names[-1]} "
        "write that the resident's income exceeds Arizona's categorical "
        f"eligibility limit; {arizona_over_names[2]} and {arizona_over_names[3]}, "
        f"along with {display['gemini-3-flash-preview']}, give "
        f"{names[arizona]}'s limit as {{azLimitBefore}}%, the limit before March.",
    )

    # The corrections. The September 3 note counted six households: four of
    # this note's five, the Michigan worker, and a second Texas household.
    worker_id, second_texan_id = "scenario_045", "scenario_112"
    assert previous["facts"]["deniedScenarios"] == sorted(
        [*full_year, worker_id, second_texan_id]
    )
    assert previous["facts"]["deniedCount"] == len(previous["facts"]["deniedScenarios"])
    previous_text = " ".join(previous["paragraphs"])
    # Its $287.68 is the unrounded minimum the references carried until the
    # r28 regeneration, which applies policyengine-us#9162's rounding.
    fixes = {
        revision["root_cause"]: revision
        for revision in reference_meta["revisions"]
        if revision.get("kind") == "upstream_fix"
    }
    min_fix = fixes["r28_snap_min_allotment_rounding"]
    assert "rounded to the nearest whole dollar" in min_fix["rule"]
    assert "PolicyEngine/policyengine-us#9162 (merged" in min_fix["upstream"]
    frozen = {
        c["scenario_id"]: c["frozen"]
        for c in min_fix["changed"]
        if c["variable"] == "snap"
    }
    assert set(frozen) == {*full_year, worker_id}
    assert len(set(frozen.values())) == 1
    previous_reference = f"{next(iter(frozen.values())):.2f}"
    # Unrounded: twelve months of it are not a whole number of dollars.
    assert not (float(previous_reference) / 12).is_integer()
    assert float(previous_reference) == previous["facts"]["referenceAnnual"]
    assert snap_exclusions[second_texan_id]["frozen_value"] == next(
        iter(frozen.values())
    )
    # The Michigan worker: scored at $0 since the r33 regeneration with
    # policyengine-us#9586, which counts the child support in gross income as
    # Michigan does; on 2.15.17 the worker's gross income exceeds Michigan's
    # BBCE limit in every month.
    r33 = fixes["r33_snap_child_support_treatment"]
    assert "PolicyEngine/policyengine-us#9586 (merged" in r33["upstream"]
    assert (
        "counts legally obligated child support paid to nonhousehold members in "
        "gross income and deducts it when computing net income"
    ) in r33["rule"]
    assert "list Michigan among those states" in r33["rule"]
    assert worker_id not in snap_exclusions and references[worker_id] == 0
    worker_row = by_id[worker_id]
    assert worker_row["state"] == "MI"
    assert set(worker_row["pathway_by_month"].split()) == {"ineligible"}
    assert worker_row["tanf_non_cash_gross_test_months"] == "0"
    assert float(worker_row["tanf_non_cash_gross_ratio_min"]) > high
    worker = _person(scenarios[worker_id], "head")
    assert worker["employment_income"] > 0 and worker["child_support_expense"] > 0
    # The version of this note published September 23 counted the worker
    # among its households; its next version, and every later one, did not.
    first = _git_json(BBCE_NOTE_FIRST_COMMIT, BBCE_NOTE_EARLIER_PATH)
    revised = _git_json(BBCE_NOTE_REVISED_COMMIT, BBCE_NOTE_EARLIER_PATH)
    assert first["slug"] == BBCE_NOTE_EARLIER and first["date"] == "2026-09-23"
    assert first["facts"]["householdCount"] == len(full_year) + 1
    assert revised["facts"]["householdCount"] == len(full_year)
    worker_link = f"/?country=us&scenario={worker_id}#scenarios"
    assert worker_link in {entry["href"] for entry in first["data"]}
    assert worker_link not in {entry["href"] for entry in revised["data"]}
    import subprocess

    later_commits = subprocess.run(
        [
            "git",
            "-C",
            str(ROOT),
            "rev-list",
            f"{BBCE_NOTE_FIRST_COMMIT}..HEAD",
            "--",
            BBCE_NOTE_EARLIER_PATH,
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert BBCE_NOTE_REVISED_COMMIT in later_commits
    # Each later commit that holds a version (the October 5 commit deletes it).
    held = 0
    for commit in later_commits:
        shown = subprocess.run(
            ["git", "-C", str(ROOT), "show", f"{commit}:{BBCE_NOTE_EARLIER_PATH}"],
            capture_output=True,
        )
        if shown.returncode != 0:
            continue
        version_then = json.loads(shown.stdout)
        assert version_then["facts"]["householdCount"] == len(full_year), commit
        assert worker_link not in {e["href"] for e in version_then["data"]}, commit
        held += 1
    assert held >= 3
    # The second Texas household: its reference assumed hours of work the
    # prompt does not list, and PolicyBench excludes it.
    second_texan = snap_exclusions[second_texan_id]
    assert second_texan["reason_code"] == "reference_depends_on_unlisted_input"
    assert second_texan["unlisted_input"] == "weekly_hours_worked_before_lsr"
    assumed_hours = re.search(
        r"the reference assumed (\d+) hours a week", second_texan["alternative_reading"]
    )
    assert assumed_hours is not None
    assert payload["scenarios"][second_texan_id]["state"] == "TX"
    for prompt in payload["scenarios"][second_texan_id]["prompt"].values():
        assert "hours" not in _household_block(prompt)
        farm_rent_lines = [
            line
            for line in _household_block(prompt).splitlines()
            if "farm rent" in line
        ]
        assert farm_rent_lines == ["- farm rent income: $1,920"]
    assert "the models counted farm-rent income the rules exclude." in previous_text
    for parameters in pathway_meta["snap_parameters"].values():
        assert "rental_income" in parameters["unearned_income_sources"]
        assert "farm_rent_income" not in parameters["unearned_income_sources"]
    # eCFR 7 CFR 273.9(b)(2)(ii) counts rental income minus business costs
    # as unearned income; (b)(1)(ii) treats rental income as self-employment
    # income when property management averages at least 20 hours a week.
    # Verified against the eCFR versioner XML for section 273.9:
    # https://www.ecfr.gov/api/versioner/v1/full/2026-10-01/title-7.xml?part=273&section=273.9
    # policyengine-us #9671 (merged October 3) adds farm rent to SNAP's
    # unearned income after this release's engine, 2.15.17.
    # The prompt does not name the source of its financial assistance, so
    # these listed facts do not establish a gross-income consequence.
    # Under the prompt's rule for unlisted numbers (0 hours), the exclusion
    # record's alternative value is the engine's $0, and the September 3
    # note's three models answered $0.
    assert second_texan["alternative_value"] == 0
    for model in TOP_MODELS:
        assert (
            payload["scenarioPredictions"][second_texan_id]["snap"][model]["prediction"]
            == 0
        )
    zero_hours = (
        "At 0 hours, as the prompt's rule for unlisted numbers reads, PolicyEngine "
        "gives that household $0, the answer "
        f"{', '.join(display[m] for m in TOP_MODELS[:-1])}, and "
        f"{display[TOP_MODELS[-1]]} gave in the September 3 note."
    )
    farm_rent_correction = (
        "The September 3 note also says SNAP excludes that household's farm "
        "rent, but SNAP counts rent, farm rent included, net of the costs of "
        "doing business: as unearned income under 7 CFR 273.9(b)(2)(ii), or as "
        "earned income under 273.9(b)(1)(ii) when a household member averages "
        "at least 20 hours a week managing the property."
    )
    farm_rent_engine = (
        "PolicyEngine counts farm rent from policyengine-us #9671, which "
        "postdates the references' engine, {engineVersion}."
    )
    pin(zero_hours, farm_rent_correction, farm_rent_engine)
    assert (
        "does not list. "
        + zero_hours
        + " "
        + farm_rent_correction
        + " "
        + farm_rent_engine
    ) in next(p for p in paragraphs if p.startswith("This note corrects "))
    # What the September 3 note said about receipt and the asset test, and
    # the four states it named.
    sept3_states = ["Connecticut", "Michigan", "Texas", "Wisconsin"]
    assert (
        f"{', '.join(sept3_states[:-1])}, and {sept3_states[-1]} confer SNAP "
        "eligibility on households receiving a TANF-funded non-cash benefit"
    ) in previous_text
    assert "and the net-income and asset tests waived." in previous_text
    assert {names[s] for s in full_year} == set(sept3_states)
    texas_asset_limit = march["TX"]["asset_limit"]
    # How PolicyEngine computed that note's amounts: its references' engine,
    # 1.755.4, is the one the September 22 pathway recomputation ran, whose
    # categorical eligibility programs read eligibility for the non-cash
    # benefit; on it, each of the four full-year households reaches its
    # $287.68 through that route, eligible for the non-cash benefit all year,
    # with no TANF and no receipt input in its scenario (above).
    meta_0922 = _load_json(PATHWAYS_0922_META_PATH)
    assert (
        previous["facts"]["referenceEngineVersion"]
        == meta_0922["policyengine_us_version"]
    )
    assert meta_0922["bbce_parameters"]["snap_categorical_eligibility_programs"] == [
        "ssi",
        "is_tanf_non_cash_eligible",
        "tanf",
    ]
    rows_0922 = {row["scenario_id"]: row for row in _read_csv(PATHWAYS_0922_PATH)}
    for scenario_id in full_year:
        row = rows_0922[scenario_id]
        assert f"{float(row['snap_frozen']):.2f}" == previous_reference
        assert abs(float(row["snap_frozen_engine"]) - float(row["snap_frozen"])) < 0.01
        assert row["tanf_non_cash_eligible_months"] == "12"
        assert float(row["tanf"]) == 0
        for column in ("pathway_jan_sep", "pathway_oct_dec"):
            assert row[column] in {"categorical_income", "categorical_both"}
    # Four of its six are this note's four full-year households.
    assert set(previous["facts"]["deniedScenarios"]) & set(households) == set(full_year)
    # The worker is over Michigan's BBCE limit (above), which is the high
    # limit the note names.
    assert "MI" in high_states
    pin(
        f"This note corrects PolicyBench's {_month_day(previous['date'])} note.",
        "That note counted {sept3HouseholdCount:words} households, "
        "{fullYearCount:words} of them among the {householdCount:words} here, at "
        "${sept3Reference} each, an amount PolicyBench computed from "
        "PolicyEngine's unrounded minimum.",
        # r28's rule and policyengine-us#9162 (above), and 2.15.17's formula,
        # read above when it is installed.
        "SNAP rounds the minimum to the nearest dollar, and so does PolicyEngine "
        "(policyengine-us #9162).",
        "One of the {sept3HouseholdCount:words}, a Michigan worker who pays "
        "child support, does not qualify.",
        # r33's rule: a state like Michigan counts the child support in gross
        # income and deducts it when computing net income (7 CFR 273.9(d)(5));
        # policyengine-us#9586 does the same, and the worker's gross income is
        # then above the 200% limit in every month (above).
        "Michigan counts that child support in gross income and deducts it when "
        "computing net income, which puts the worker's gross income above "
        "Michigan's {bbceGrossLimitHigh}% BBCE limit; PolicyEngine subtracted it "
        "from gross income until policyengine-us #9586.",
        f"The version of this note published {_month_day(first['date'])} "
        "counted the worker among its households.",
        "PolicyBench no longer scores another of the "
        "{sept3HouseholdCount:words}, a second Texas household, whose "
        "reference assumed {assumedHours} hours of work a week that the prompt "
        "does not list.",
        # Its text says receipt; its amounts came from eligibility (above).
        f"The {_month_day(previous['date'])} note described BBCE as covering "
        "households that receive the non-cash benefit, but PolicyEngine computed "
        "that note's amounts by applying BBCE to every household eligible for that "
        "benefit.",
        f"It also said {', '.join(sept3_states[:-1])}, and {sept3_states[-1]} "
        f"waive the asset test, but {texas} keeps a ${{bbceAssetLimitTx}} asset "
        "limit.",
    )

    # The September 3 note links this one and points to it in its last
    # paragraph (test_september_3_note_describes_the_later_release pins it).
    previous_links = {entry["label"]: entry["href"] for entry in previous["data"]}
    assert (
        previous_links[f"Later note on these households ({_month_day(note['date'])})"]
        == f"/notes/{note['slug']}"
    )
    assert previous["paragraphs"][-1].startswith(
        f"A later note, published {_month_day(note['date'])}, corrects this one. "
    )

    # The models the prose names by hand, and no sentence left unpinned.
    assert _named_models(text, display) == {
        "gpt-5.5",
        zero_tanf_model,
        "gpt-5.6-sol",
        # The September 3 note's three models, named in the corrections.
        "claude-fable-5.1",
        "kimi-k3",
        "gpt-6-luna",
        "gemini-3-flash-preview",
        "gemini-3.1-pro-preview",
        "gpt-6-astra",
        "gpt-6.1-sol",
        "claude-opus-5.5",
        "gpt-6-sol",
        "claude-sonnet-5.5",
        "gemini-3.5-flash",
        "gemini-3.8-flash",
    }
    unpinned = text
    for sentence in pinned:
        unpinned = unpinned.replace(sentence, "", 1)
    assert not unpinned.strip(), unpinned

    # The data links name each household as the prose does, and count the
    # households of each group (every link resolves, above).
    household_links = {
        f"{texas} resident": texas_id,
        f"{names[couple_id]} couple": couple_id,
        f"Disabled {names[michigan_id]} resident": michigan_id,
        f"{names[wisconsin_id]} surviving spouse": wisconsin_id,
        f"{names[arizona]} resident": arizona,
    }
    assert sorted(household_links.values()) == households
    for label, scenario_id in household_links.items():
        assert links[label] == f"/?country=us&scenario={scenario_id}#scenarios"
    assert not any(re.search(r"scenario_\d", label) for label in links)
    assert not any(worker_id in href for href in links.values())
    number_words = {4: "four", 5: "five"}
    assert (
        links[
            f"Every model's answer for the {number_words[len(households)]} "
            "households held back by income"
        ]
        == blob + BBCE_ROWS_PATH.relative_to(ROOT).as_posix()
    )
    assert (
        links[
            f"Every model's answer for the {number_words[len(savings_households)]} "
            "households held back by savings"
        ]
        == blob + BBCE_ASSET_ROWS_PATH.relative_to(ROOT).as_posix()
    )
    assert links["SNAP pathways under the release's references"] == (
        blob + PATHWAYS_0930_PATH.relative_to(ROOT).as_posix()
    )
    assert links["Reference upgrade record"] == (
        blob + "reference_audit/2026-09-28/README.md"
    )
    assert (
        links["Exclusion record"] == blob + EXCLUSIONS_PATH.relative_to(ROOT).as_posix()
    )
    for label, slug in (
        (f"Six SNAP households note ({_month_day(previous['date'])})", SNAP_NOTE),
        ("Reference audit note (September 22)", AUDIT_NOTE),
        ("Release note for dashboard-data-20260929 (September 29)", RELEASE_NOTE),
    ):
        assert links[label] == f"/notes/{slug}"
        assert _note(slug)["slug"] == slug

    derived = {
        "householdCount": len(households),
        "nModels": len(board),
        "minimumMonthly": _whole_or_cents(minimum),
        "minimumFromOctober": _whole_or_cents(minimum_from_october),
        "referenceAmount": _whole_or_cents(reference_amount),
        "fullYearCount": len(full_year),
        "azReference": _whole_or_cents(references[arizona]),
        "answers": len(rows),
        "zeroAnswers": len(zero_rows),
        "hits": sum(row["within_1_dollar"] for row in rows),
        "snapGrossLimit": round(100 * snap_gross_limit),
        "bbceGrossLimitHigh": high_limit,
        "bbceGrossLimitTx": round(100 * texas_limit),
        "azLimitBefore": round(100 * az_before),
        "wiAge": widow["age"],
        "azAge": arizonan["age"],
        "txAge": texan["age"],
        "financialAssistance": _whole_or_cents(financial_assistance),
        "ctSavings": _whole_or_cents(savings),
        "azSavings": _whole_or_cents(arizona_savings),
        "zeroTanfMentions": len(zero_tanf),
        "assetOnlyCount": len(savings_households),
        "assetOnlyAbove0Share": _percent(len(asset_above_zero), len(asset_returned)),
        "incomeAbove0Share": _percent(len(above_zero), len(returned)),
        "sol56Rank": _rank(by_model["gpt-5.6-sol"]["exact"], board),
        "lunaRank": _rank(by_model["gpt-6-luna"]["exact"], board),
        "splitModels": len(split_models),
        "assetOnlyBbceMentions": len(asset_mentions),
        "assetOnlyExplanations": len(asset_explained),
        "assetOnlyBbceAssets": sum(row["mentions_assets"] for row in asset_mentions),
        "incomeBbceMentions": len(income_mentions),
        "explanations": len(explained),
        "incomeBbceZeros": len(income_mention_zeros),
        "incomeBbceZeroOverLimit": len(over_limit),
        "overLimitAz": sum(s == arizona for _, s in over_limit),
        "overLimitTx": sum(s == texas_id for _, s in over_limit),
        "netLimitOnly": len(net_only),
        "formulaOnly": len(formula_only),
        "incomeBbceAbove0": len(above_mentions),
        "incomeBbceHits": len(income_hits),
        "staleMinimum": len(stale),
        "fy2025Minimum": fy2025_minimum,
        "fy2025MinimumAnnual": _whole_or_cents(stale_annual),
        "astraHits": best,
        "sol61Hits": len(sol61_hits),
        "opusOn108": _whole_or_cents(opus[wisconsin_id]),
        "sol6ZeroCount": sum(value == 0 for value in sol6.values()),
        "sol6BbceMentions": bbce_mentions("gpt-6-sol"),
        "boardHouseholds": board_households,
        "sol6On030": _whole_or_cents(texas_answers["gpt-6-sol"]),
        "opusOn030": _whole_or_cents(texas_answers["claude-opus-5.5"]),
        "engineVersion": engine,
        "sept3HouseholdCount": previous["facts"]["deniedCount"],
        "sept3Reference": previous_reference,
        "assumedHours": int(assumed_hours.group(1)),
        "bbceAssetLimitTx": _whole_or_cents(texas_asset_limit),
    }
    return derived


@pytest.mark.slow
def test_snap_pathways_20260930_regenerates() -> None:
    """Rerun the pathway recomputation on the references' engine and compare it
    with the committed CSV and meta, which the BBCE note test reads.

    It runs on policyengine-us 2.15.17, which the repository pins, and skips
    on any other version; it is marked slow, so CI deselects it. Run it with

      OPENBLAS_NUM_THREADS=1 uv run pytest -m slow tests/test_notes.py \\
        -k 20260930_regenerates
    """
    from importlib.metadata import PackageNotFoundError, version

    committed_meta = _load_json(PATHWAYS_0930_META_PATH)
    needed = committed_meta["policyengine_us_version"]
    try:
        engine = version("policyengine-us")
    except PackageNotFoundError:
        pytest.skip("policyengine-us is not installed")
    if engine != needed:
        pytest.skip(f"needs policyengine-us {needed}, found {engine}")
    sys.path.insert(0, str(ROOT / "scripts"))
    from snap_pathways_20260930 import build, csv_text

    rows, meta = build()
    assert csv_text(rows) == PATHWAYS_0930_PATH.read_bytes().decode("utf-8")
    regenerated = json.loads(json.dumps(meta))
    for record in (regenerated, committed_meta):
        record.pop("generated_at_utc")
    assert regenerated == committed_meta


# The release that superseded dashboard-data-20260922 on the same snapshot,
# which the September 22 notes' closing paragraphs describe, and the interim
# release between them.
LATER_RELEASE = "dashboard-data-20260922c"
INTERIM_RELEASE = "dashboard-data-20260922b"


def _later_facts(note: dict) -> dict:
    return {k: v for k, v in note["facts"].items() if k.startswith("later")}


def test_september_22_notes_point_to_the_later_release() -> None:
    """The two September 22 notes keep the facts of their release and close
    with the figures of the release that replaced it, recomputed here while
    that release is the frozen one."""
    sol, audit = _note(SOL6_NOTE), _note(AUDIT_NOTE)
    opening = (
        f"A later release, {LATER_RELEASE}, corrects the reference for one "
        "output: the SNAP amount of a Michigan worker who pays child support."
    )
    interim = (
        f"An interim release, {INTERIM_RELEASE}, excluded that output while the "
        "fix was open."
    )
    for note in (sol, audit):
        assert note["release"] == "dashboard-data-20260922"
        assert note["paragraphs"][-1].startswith(opening + " ")
        assert note["paragraphs"][-1].endswith(" " + interim)
        assert not any(LATER_RELEASE in p for p in note["paragraphs"][:-1])
        links = {entry["label"]: entry["href"] for entry in note["data"]}
        assert links[f"Later release {LATER_RELEASE}"] == (
            "https://github.com/PolicyEngine/policybench/releases/tag/" + LATER_RELEASE
        )
    if _frozen_release() != LATER_RELEASE:
        return

    # The same exclusions as the notes' release: the interim release's one
    # extra exclusion is gone, and no exclusion postdates the notes.
    exclusions = _load_json(EXCLUSIONS_PATH)["exclusions"]
    assert len(exclusions) == sol["facts"]["excluded"]
    assert not [e for e in exclusions if e["decided_on"] > sol["date"]]
    payload = _dashboard()
    assert payload["scenarios"]["scenario_045"]["state"] == "MI"
    head = next(
        person
        for person in json.loads(
            next(
                row["scenario_json"]
                for row in csv.DictReader(
                    (RUN_DIR / "scenarios.csv").open(encoding="utf-8", newline="")
                )
                if row["scenario_id"] == "scenario_045"
            )
        )["adults"]
        if person["name"] == "head"
    )
    assert head["inputs"]["child_support_expense"] > 0 and head["employment_income"] > 0
    # The worker's SNAP reference is regenerated at $0 with the merged fix;
    # the notes' release had regenerated it at $288 with r28 alone.
    assert _snap_references()["scenario_045"] == 0
    meta = _load_json(REFERENCE_META_PATH)
    r33 = next(
        revision
        for revision in meta["revisions"]
        if revision.get("root_cause") == "r33_snap_child_support_treatment"
    )
    assert r33["kind"] == "upstream_fix" and "#9586" in r33["upstream"]
    assert "merged" in r33["upstream"]
    assert [
        (c["scenario_id"], c["variable"], c["regenerated"]) for c in r33["changed"]
    ] == [("scenario_045", "snap", 0.0)]

    # The audit note: one more root cause fixed upstream, every other count
    # the same.
    audit_now = _reference_audit_facts()
    assert _later_facts(audit) == {"laterUpstreamFixed": audit_now["upstreamFixed"]}
    assert audit_now["upstreamFixed"] - audit["facts"]["upstreamFixed"] == 1
    for key, value in audit_now.items():
        if key != "upstreamFixed":
            assert audit["facts"][key] == value, key
    assert audit["paragraphs"][-1] == (
        opening + " policyengine-us subtracted that child support from gross "
        "income, while Michigan counts it in gross income and deducts it only "
        "when computing net income. PolicyEngine fixed this after the audit "
        "(policyengine-us #9586), so the later release regenerates the output "
        "with the fix: counted in gross income, the worker's income exceeds "
        "Michigan's broad-based categorical eligibility limit, and the reference "
        "is $0 instead of $288. That makes {laterUpstreamFixed} root causes "
        "fixed upstream; every other count in this note stays the same. " + interim
    )
    assert {entry["label"]: entry["href"] for entry in audit["data"]}[
        "Later note on the SNAP households that qualify through BBCE (October 5)"
    ] == f"/notes/{BBCE_NOTE}"

    # The GPT-6 Sol note: the figures that moved, and every other figure the
    # same on the later release.
    sol_now = _gpt6_sol_facts()
    assert _later_facts(sol) == {
        "laterSolExact": sol_now["solExact"],
        "laterOpusExact": sol_now["opusExact"],
        "laterOpus5AutoExact": sol_now["opus5AutoExact"],
    }
    moved = {"solExact", "opusExact", "opus5AutoExact"}
    for key, value in sol_now.items():
        if key not in moved:
            assert sol["facts"][key] == value, key
    # "The other scores, gaps, ranks and costs": every unchanged figure is one
    # of those, apart from the model and output counts ("the same outputs ...
    # references ... outputs").
    unchanged = set(sol_now) - moved
    kinds = {"Exact": "score", "Lead": "gap", "Gap": "gap", "Rank": "rank"}
    kinds["Cost"] = "cost"
    assert {k for k in unchanged if not k.endswith(tuple(kinds))} == {
        "nModels",
        "totalOutputs",
        "scoredOutputs",
        "regenerated",
        "excluded",
    }
    assert {kinds[s] for k in unchanged for s in kinds if k.endswith(s)} == {
        "score",
        "gap",
        "rank",
        "cost",
    }
    assert sol["paragraphs"][-1] == (
        opening + " PolicyEngine had subtracted that child support from the "
        "worker's gross income; with its fix (policyengine-us #9586) the worker "
        "does not qualify, and the reference is $0 instead of $288. The later "
        "release scores the same outputs, regenerates the same references and "
        "excludes the same outputs as this one. On it, GPT-6 Sol scores "
        "{laterSolExact}% and Claude Opus 5.5 {laterOpusExact}%, and Claude Opus "
        "5's tool_choice auto re-run scores {laterOpus5AutoExact}%. The note's "
        "other scores, gaps, ranks and costs stay the same. " + interim
    )


def test_september_3_note_describes_the_later_release() -> None:
    """The September 3 note closes by pointing to the October 5 note, which
    corrects it, and by stating how PolicyBench scores its six households
    from release dashboard-data-20260922c on. No reference revision after
    that release changes any of their SNAP references, and no exclusion of
    any of them postdates it, so the frozen release's references and
    exclusions for the six are 20260922c's and recompute the paragraph's
    figures."""
    previous, bbce = _note(SNAP_NOTE), _note(BBCE_NOTE)
    later_note = _month_day(bbce["date"])
    assert previous["paragraphs"][-1] == (
        f"A later note, published {later_note}, corrects this one. From release "
        f"{LATER_RELEASE} on, PolicyBench scores the SNAP amounts of "
        "{laterScoredCount:words} of these {deniedCount:words} households at "
        "${laterReference} each, and scores a Michigan worker who pays child "
        "support at $0: PolicyEngine counts that child support in gross "
        "income, as Michigan does (policyengine-us #9586), and the worker does not "
        "qualify. PolicyBench no longer scores a Texas household's SNAP amount, "
        "which PolicyEngine computed with hours of work the prompt does not list."
    )
    assert not any(LATER_RELEASE in p for p in previous["paragraphs"][:-1])
    links = {entry["label"]: entry["href"] for entry in previous["data"]}
    assert links[f"Later note on these households ({later_note})"] == (
        f"/notes/{BBCE_NOTE}"
    )
    assert links[f"Later release {LATER_RELEASE}"] == (
        "https://github.com/PolicyEngine/policybench/releases/tag/" + LATER_RELEASE
    )

    # Release 20260922c carries the audit's revisions, all dated September 22;
    # none of the later ones, the engine upgrade of 20260929 among them,
    # changes the six's SNAP references.
    audit_day = "2026-09-22"
    denied = previous["facts"]["deniedScenarios"]
    meta = _load_json(REFERENCE_META_PATH)
    later = [r for r in meta["revisions"] if r["date"] > audit_day]
    assert "engine_upgrade" in {r.get("kind") for r in later}
    for revision in later:
        assert not {
            c["scenario_id"]
            for c in revision.get("changed", [])
            if c["variable"] == "snap"
        } & set(denied)
    snap_exclusions = {
        e["scenario_id"]: e
        for e in _load_json(EXCLUSIONS_PATH)["exclusions"]
        if e["variable"] == "snap"
    }
    for scenario_id in set(denied) & set(snap_exclusions):
        assert snap_exclusions[scenario_id]["decided_on"] <= audit_day
    references = _snap_references()
    scored = [s for s in denied if s not in snap_exclusions]
    at_minimum = [s for s in scored if references[s] > 0]
    # Four of the six are scored at $288, the Michigan worker at $0, and the
    # second Texas household stays excluded (unlisted hours of work).
    assert {references[s] for s in at_minimum} == {previous["facts"]["laterReference"]}
    assert previous["facts"]["laterReference"] == 288
    assert previous["facts"]["laterScoredCount"] == len(at_minimum) == 4
    assert previous["facts"]["deniedCount"] == len(denied) == 6
    assert sorted(set(scored) - set(at_minimum)) == ["scenario_045"]
    assert references["scenario_045"] == 0
    assert sorted(set(denied) - set(scored)) == ["scenario_112"]
    assert snap_exclusions["scenario_112"]["unlisted_input"] == (
        "weekly_hours_worked_before_lsr"
    )
    payload = _dashboard()
    assert payload["scenarios"]["scenario_045"]["state"] == "MI"
    assert payload["scenarios"]["scenario_112"]["state"] == "TX"
    r33 = next(
        r
        for r in meta["revisions"]
        if r.get("root_cause") == "r33_snap_child_support_treatment"
    )
    assert "PolicyEngine/policyengine-us#9586 (merged" in r33["upstream"]
    assert [(c["scenario_id"], c["regenerated"]) for c in r33["changed"]] == [
        ("scenario_045", 0.0)
    ]


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

    # The pathway files belong to release dashboard-data-20260922b, which the
    # September 23 version of the BBCE note read; once a later release is
    # frozen, the committed references they were checked against are in git
    # history, not in the snapshot this test reads.
    if _frozen_release() != INTERIM_RELEASE:
        pytest.skip("the pathway files belong to a superseded release")
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


# ----- Release dashboard-data-20260929 --------------------------------------

RELEASE_NOTE = "2026-09-29-claude-sonnet-5-5-debuts-fifth"
ADDED_MODELS = ("claude-sonnet-5.5", "grok-4.7", "deepseek-v4.1-flash")
# Release dashboard-data-20260929 was frozen by the merge of #182. Its note's
# facts are recomputed from the snapshot that commit holds, read from git, so
# they stay checked against their own release after a later one is frozen
# (RELEASE_20260929_COMMIT, with the other releases' commits, is above).
RELEASE_20260929 = "dashboard-data-20260929"
SERVING_CONFIG_PATH = SNAPSHOT_DIR / "model_serving_config.json"
UPGRADE_README = ROOT / "reference_audit/2026-09-28/README.md"
UPGRADE_CLUSTERS = ROOT / "reference_audit/2026-09-28/clusters.json"
UPGRADE_ACTIONS = ROOT / "reference_audit/2026-09-28/final_actions.json"
# The one output the audit excluded outside the engine revision, and the probe
# that computed both readings of it on policyengine-us 2.15.17.
MEDICAID_EXCLUSION = ("scenario_023", "head_medicaid_eligible")
MEDICAID_PROBE_PATH = (
    ROOT / "reference_audit/2026-09-28/verification/probe_023_medicaid.json"
)
# The no-tools exact scores release dashboard-data-20260922c published, copied
# from its release asset by scripts/release_20260922c_scores.py. The asset's
# sha256 is the one app/src/data.artifact.json pinned at commit 3220a7a6.
PREVIOUS_RELEASE = "dashboard-data-20260922c"
PREVIOUS_SCORES_PATH = ROOT / "notes/data/release_20260922c_exact.csv"
PREVIOUS_SCORES_META_PATH = PREVIOUS_SCORES_PATH.with_suffix(".csv.meta.json")
PREVIOUS_ASSET_SHA256 = (
    "01e7e72b3a6bdd2d3178ba32625ff769d5b81dc07541af6ea8da2c852774ddcc"
)
# The verification sweep on the newest policyengine-us release when
# PolicyBench checked PyPI before publishing.
PUBLICATION_CHECK_PATH = (
    ROOT / "reference_audit/2026-09-28/verification/latest_final_2170.csv"
)
# policyengine-us upload times on PyPI, as the upgrade's timing record read
# them (reference_audit/2026-09-28/verification/sweep_timing.json, which
# tests/test_reference_upgrade.py checks against the sweep and the build).
SWEEP_TIMING = json.loads(
    (ROOT / "reference_audit/2026-09-28/verification/sweep_timing.json").read_text()
)
ENGINE_UPLOADED_UTC = {
    version: uploaded[11:16]
    for version, uploaded in SWEEP_TIMING["pypi"]["wheel_uploaded_at_utc"].items()
}
# When PolicyBench read PyPI for the publication check, and the newest
# release it found then.
PYPI_READ_AT_UTC = SWEEP_TIMING["pypi"]["read_at_utc"]
PYPI_NEWEST_AT_READ = SWEEP_TIMING["pypi"]["newest_at_read"]
ORDINALS = {
    1: "first",
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
    8: "eighth",
    9: "ninth",
    10: "tenth",
}
# The engine upgrade's scored changes, keyed by the household's state.
UPGRADE_CHANGES = {
    "NJ": ("scenario_008", "state_refundable_credits"),
    "AZ": ("scenario_013", "snap"),
    "PA": ("scenario_028", "reduced_price_school_meals_eligible"),
    "NY": ("scenario_082", "state_refundable_credits"),
}


def _snapshot_20260929_root() -> Path:
    """A scratch tree holding paper/snapshot/20260501 exactly as
    RELEASE_20260929_COMMIT has it."""
    return _snapshot_root(RELEASE_20260929_COMMIT)


def _at_20260929(path: Path) -> Path:
    """A snapshot file as release 20260929's commit holds it."""
    return _in(_snapshot_20260929_root(), path)


def _dashboard_20260929() -> dict:
    return _payload_at(_snapshot_20260929_root())


def _release_20260929_tag() -> str:
    """The tag release 20260929's manifest names, after checking that it pins
    the payload its commit holds."""
    manifest = _load_json(_at_20260929(SNAPSHOT_DIR / "manifest.json"))
    payload = run_payload_path(_at_20260929(RUN_DIR))
    assert manifest["files"] == [
        {
            "path": payload.relative_to(_at_20260929(SNAPSHOT_DIR)).as_posix(),
            "sha256": _sha256_file(payload),
        }
    ]
    assert manifest["snapshot_date"] == SUPERSEDED_RELEASES[RELEASE_20260929]
    return manifest["published_dashboard_artifact"]["tag"]


def _engine_upgrade() -> dict:
    meta = _load_json(_at_20260929(REFERENCE_META_PATH))
    return next(r for r in meta["revisions"] if r.get("kind") == "engine_upgrade")


def _board_rows() -> list[dict]:
    return [
        row
        for row in _dashboard_20260929()["modelStats"]
        if row["condition"] == "no_tools"
    ]


@cache
def _previous_release_scores() -> dict[str, float]:
    """Every model's exact score as release dashboard-data-20260922c published
    it, from the committed fixture, checked against its record."""
    import hashlib

    meta = _load_json(PREVIOUS_SCORES_META_PATH)
    assert meta["release"] == PREVIOUS_RELEASE
    assert meta["asset_sha256"] == PREVIOUS_ASSET_SHA256
    assert meta["pointer"].endswith("3220a7a62b6be83032e9313c9df539c619ad8932")
    assert (
        hashlib.sha256(PREVIOUS_SCORES_PATH.read_bytes()).hexdigest()
        == meta["output_sha256"]
    )
    with PREVIOUS_SCORES_PATH.open(encoding="utf-8", newline="") as source:
        scores = {row["model"]: float(row["exact"]) for row in csv.DictReader(source)}
    assert len(scores) == meta["rows"]
    return scores


def _models_moving_up(
    before: dict[str, float], after: dict[str, float]
) -> list[tuple[str, list[str]]]:
    """Each model that moves above others, in its new order, with the models it
    passes, in their old order. Every pair of models whose order changes is one
    riser and one model it passes, so every other pair keeps its order."""
    old = {m: i for i, m in enumerate(sorted(before, key=lambda m: -before[m]))}
    new = {m: i for i, m in enumerate(sorted(before, key=lambda m: -after[m]))}
    passes: dict[str, list[str]] = {}
    for riser in before:
        for passed in before:
            if old[riser] > old[passed] and new[riser] < new[passed]:
                passes.setdefault(riser, []).append(passed)
    # A model that passes one model is not itself passed by a third: each
    # change reads as risers moving up past the models just above them.
    assert not set(passes) & {m for passed in passes.values() for m in passed}
    return [
        (riser, sorted(passes[riser], key=old.__getitem__))
        for riser in sorted(passes, key=new.__getitem__)
    ]


def _and(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


@cache
def _exact_under(
    previous_release: bool, *, score_audit_exclusions: bool = False
) -> dict[str, float]:
    """Every board model's exact score, recomputed from this snapshot's
    predictions and weights on the current references or on the previous
    release's: the references with the engine upgrade's changes reverted to
    their previous values, scored without the exclusions it added or the
    audit's (final_actions.json audit_exclusions). With
    ``score_audit_exclusions``, the current references are scored with the
    audit's exclusions put back, which isolates the audit's effect."""
    import pandas as pd

    from policybench.scorer_vectors import canonical_filtered_scores
    from policybench.spec import output_group_id

    payload = _dashboard_20260929()
    reference = pd.read_csv(_at_20260929(REFERENCES_PATH))
    changes = _engine_upgrade()["changed"]
    added = {(c["scenario_id"], c["variable"]) for c in changes}
    excluded = {
        (e["scenario_id"], e["variable"])
        for e in _load_json(_at_20260929(EXCLUSIONS_PATH))["exclusions"]
    }
    audit = {
        (a["scenario_id"], a["variable"])
        for a in _load_json(UPGRADE_ACTIONS).get("audit_exclusions", [])
    }
    if previous_release:
        for change in changes:
            row = (reference["scenario_id"] == change["scenario_id"]) & (
                reference["variable"] == change["variable"]
            )
            assert row.sum() == 1
            reference.loc[row, "value"] = change["previous"]
        excluded -= added | audit
    elif score_audit_exclusions:
        excluded -= audit
    keys = zip(reference["scenario_id"], reference["variable"], strict=True)
    scored = reference[[key not in excluded for key in keys]]
    predictions = pd.DataFrame(
        [
            (model, scenario_id, variable, entry.get("prediction"))
            for scenario_id, outputs in payload["scenarioPredictions"].items()
            for variable, by_model in outputs.items()
            for model, entry in by_model.items()
        ],
        columns=["model", "scenario_id", "variable", "prediction"],
    )
    weights: dict[str, float] = {}
    for variable, weight in payload["globalWeights"]["household"].items():
        group = output_group_id(variable)
        weights[group] = weights.get(group, 0.0) + weight
    scores, _ = canonical_filtered_scores(
        scored, predictions, weights, set(weights), "all", "exact"
    )
    return scores


@cache
def _added_model_responses() -> dict[str, dict]:
    """Per added model: its answer rows in the frozen predictions, and the
    model names and system fingerprints the provider reported on them."""
    seen = {
        model: {"rows": 0, "resolved": set(), "fingerprints": set()}
        for model in ADDED_MODELS
    }
    with gzip.open(
        _at_20260929(PREDICTIONS_PATH), "rt", encoding="utf-8", newline=""
    ) as source:
        for row in csv.DictReader(source):
            record = seen.get(row["model"])
            if record is None:
                continue
            record["rows"] += 1
            record["resolved"].add(row["provider_resolved_model"])
            record["fingerprints"].add(row["provider_system_fingerprint"])
    return seen


def _matches(prediction: float | None, reference: float) -> bool:
    return prediction is not None and abs(prediction - reference) <= 1


def _release_20260929_facts() -> dict:
    """The release note's facts, computed on release 20260929's snapshot."""
    import math

    from policybench.paper_results import MODEL_DISPLAY_NAMES

    rows = _board_rows()
    by_model = {row["model"]: row for row in rows}
    sonnet, grok, flash = (by_model[m] for m in ADDED_MODELS)
    luna, sol = by_model["gpt-6-luna"], by_model["gpt-6-sol"]
    opus, sol56 = by_model["claude-opus-5.5"], by_model["gpt-5.6-sol"]
    serving = _load_json(_at_20260929(SERVING_CONFIG_PATH))["models"]
    meta = _load_json(_at_20260929(REFERENCE_META_PATH))
    upgrade = _engine_upgrade()
    exclusions = _load_json(_at_20260929(EXCLUSIONS_PATH))["exclusions"]
    excluded = {(e["scenario_id"], e["variable"]) for e in exclusions}
    changes = {(c["scenario_id"], c["variable"]): c for c in upgrade["changed"]}
    scored_changes = {
        key: change
        for key, change in changes.items()
        if key not in excluded and key in UPGRADE_CHANGES.values()
    }
    within_tolerance = [
        change
        for key, change in changes.items()
        if key not in excluded and key not in scored_changes
    ]
    # The verification sweep on the newest release when PolicyBench read PyPI.
    with PUBLICATION_CHECK_PATH.open(encoding="utf-8", newline="") as source:
        (check_engine,) = {row["engine"] for row in csv.DictReader(source)}
    assert check_engine == PYPI_NEWEST_AT_READ
    # The BBCE note's households on this release (its September 29 data
    # files): held back by income, the Arizona household among them, and held
    # back by savings.
    payload = _dashboard_20260929()
    income_held = _load_json(
        ROOT / "notes/data/bbce_households_20260929.csv.meta.json"
    )["households"]
    savings_held = _load_json(
        ROOT / "notes/data/bbce_asset_households_20260929.csv.meta.json"
    )["households"]
    assert UPGRADE_CHANGES["AZ"][0] in income_held
    bbce_states = [
        STATE_NAMES[payload["scenarios"][s]["state"]]
        for s in income_held
        if s != UPGRADE_CHANGES["AZ"][0]
    ]
    # The revision's own new exclusions: outputs it changed that left scoring.
    new_exclusions = [change for key, change in changes.items() if key in excluded]
    assert set(scored_changes) == set(UPGRADE_CHANGES.values())
    assert all(abs(c["regenerated"] - c["previous"]) <= 1 for c in within_tolerance)

    def before_after(state: str) -> tuple[int | str, int | str]:
        change = scored_changes[UPGRADE_CHANGES[state]]
        return (
            _whole_or_cents(change["previous"]),
            _whole_or_cents(change["regenerated"]),
        )

    # The incumbents: the models release 20260922c published, with the scores
    # it published, against their scores on this release's references.
    before = _previous_release_scores()
    incumbents = sorted(before)
    assert set(by_model) - set(incumbents) == set(ADDED_MODELS)
    after = {m: by_model[m]["exact"] for m in incumbents}
    drift = [after[m] - before[m] for m in incumbents]
    risers = _models_moving_up(before, after)
    # The audit's exclusion (final_actions.json audit_exclusions): the
    # California household head's Medicaid eligibility, with the head's MAGI
    # as a share of the poverty guideline from the probe behind it, and how
    # the incumbents had answered it.
    (audit,) = _load_json(UPGRADE_ACTIONS)["audit_exclusions"]
    medicaid = (audit["scenario_id"], audit["variable"])
    assert medicaid == MEDICAID_EXCLUSION and medicaid in excluded
    probe = _load_json(MEDICAID_PROBE_PATH)
    stated = probe["results"]["latest_final/stated_facts"]
    expansion = re.search(
        r"above the (\d+)% limit for the adult expansion group",
        audit["exclusion"]["alternative_reading"],
    )
    assert expansion is not None
    medicaid_answers = payload["scenarioPredictions"][medicaid[0]][medicaid[1]]
    medicaid_reference = next(
        e["frozen_value"]
        for e in exclusions
        if (e["scenario_id"], e["variable"]) == medicaid
    )
    # A 0/1 flag matches only when equal; the $1 tolerance is for amounts.
    matched = [
        m
        for m in incumbents
        if medicaid_answers[m].get("prediction") == medicaid_reference
    ]

    derived = {
        "nModels": len(rows),
        "sonnetExact": _display_one_decimal(sonnet["exact"]),
        "sonnetRank": _rank(sonnet["exact"], rows),
        "lunaExact": _display_one_decimal(luna["exact"]),
        "lunaRank": _rank(luna["exact"], rows),
        # "less than {gap} points ahead": the gap rounded up to hundredths.
        "lunaSonnetGapBelow": math.ceil((luna["exact"] - sonnet["exact"]) * 100) / 100,
        "grokExact": _display_one_decimal(grok["exact"]),
        "grokRank": _rank(grok["exact"], rows),
        "flashExact": _display_one_decimal(flash["exact"]),
        "flashRank": _rank(flash["exact"], rows),
        "solExact": _display_one_decimal(sol["exact"]),
        "opusExact": _display_one_decimal(opus["exact"]),
        "sol56Exact": _display_one_decimal(sol56["exact"]),
        "sonnetCost": _cost_per_household(sonnet),
        "lunaCost": _cost_per_household(luna),
        "flashCost": _cost_per_household(flash),
        "grokCost": _cost_per_household(grok),
        "grokTimeoutSeconds": serving["grok-4.7"]["request_timeout_seconds"],
        "flashAnswers": _added_model_responses()["deepseek-v4.1-flash"]["rows"],
        "previousEngine": upgrade["previous_engine_version"].removeprefix(
            "policyengine-us "
        ),
        "engineVersion": upgrade["engine_version"].removeprefix("policyengine-us "),
        "upstreamFixed": sum(
            1 for r in meta["revisions"] if r.get("kind") == "upstream_fix"
        ),
        "conventions": sum(
            1 for r in meta["revisions"] if r.get("kind", "convention") == "convention"
        ),
        "scoredChanges": len(scored_changes),
        "njBefore": before_after("NJ")[0],
        "njAfter": before_after("NJ")[1],
        "azBefore": before_after("AZ")[0],
        "azAfter": before_after("AZ")[1],
        "nyBefore": before_after("NY")[0],
        "nyAfter": before_after("NY")[1],
        "newExclusions": len(new_exclusions),
        "scoredOutputs": sonnet["n"],
        "totalOutputs": sum(1 for _ in open(_at_20260929(REFERENCES_PATH))) - 1,
        "engineUploadedUtc": ENGINE_UPLOADED_UTC[
            upgrade["engine_version"].removeprefix("policyengine-us ")
        ],
        "checkEngine": check_engine,
        "checkPypiReadUtc": PYPI_READ_AT_UTC[11:16],
        "bbceIncomeHeldStates": ", ".join(bbce_states[:-1]) + " and " + bbce_states[-1],
        "bbceIncomeHeldCount": len(bbce_states),
        "bbceAssetHeldCount": len(savings_held),
        "excluded": len(exclusions),
        "withinTolerance": len(within_tolerance),
        "rechecked": len(upgrade["excluded_outputs_rechecked"]),
        "incumbents": len(incumbents),
        "driftMin": round(min(drift), 2),
        "driftMax": round(max(drift), 2),
        "medicaidMatched": len(matched),
        "medicaidMissed": len(incumbents) - len(matched),
        "riserCount": len(risers),
        "medicaidIncomePercent": round(100 * stated["medicaid_income_level"]),
        "expansionLimitPercent": int(expansion.group(1)),
    }
    for ordinal, (riser, passed) in zip(
        ("One", "Two", "Three", "Four", "Five"), risers, strict=True
    ):
        derived[f"riser{ordinal}"] = MODEL_DISPLAY_NAMES[riser]
        derived[f"riser{ordinal}Passed"] = _and(
            [MODEL_DISPLAY_NAMES[m] for m in passed]
        )
    # Grok 4.7's card records the timeout its onboarding probe ran past.
    from policybench.model_cards import MODEL_CARDS

    onboarding = re.search(
        r"A first attempt with a (\d+)s timeout", MODEL_CARDS["xai/grok-4.7"].notes
    )
    assert onboarding is not None
    derived["grokOnboardingTimeoutSeconds"] = int(onboarding.group(1))
    # Arizona's limits, as the reference sidecar records the change.
    arizona = re.search(
        r"from (\d+)% to (\d+)% of poverty from benefit month 03/2026",
        scored_changes[UPGRADE_CHANGES["AZ"]]["basis"],
    )
    assert arizona is not None
    derived["azLimitBefore"] = int(arizona.group(1))
    derived["azLimitAfter"] = int(arizona.group(2))
    assert len(risers) == 5
    assert {row["n"] for row in rows} == {derived["scoredOutputs"]}
    return derived


def test_release_20260929_note() -> None:
    """The September 29 release note: its facts recompute from release
    20260929's snapshot, as its commit holds it, and every sentence is pinned
    beside the evidence for it."""
    from policybench.model_cards import MODEL_CARDS
    from policybench.paper_results import MODEL_DISPLAY_NAMES, MODEL_RELEASE_DATES

    note = _note(RELEASE_NOTE)
    assert note["release"] == RELEASE_20260929
    facts = note["facts"]
    assert facts == _release_20260929_facts()
    text = " ".join(note["paragraphs"])
    pinned: list[str] = []

    def pin(*sentences: str) -> None:
        for sentence in sentences:
            assert text.count(sentence) == 1, sentence
            pinned.append(sentence)

    rows = _board_rows()
    by_model = {row["model"]: row for row in rows}
    display = {m: MODEL_DISPLAY_NAMES[m] for m in by_model}

    # The three additions are the models release 20260922c lacked, and it
    # published every other board model.
    previous = _previous_release_scores()
    assert set(by_model) - set(previous) == set(ADDED_MODELS)
    assert set(previous) <= set(by_model)
    assert len(previous) == facts["incumbents"] == 42
    # The title: Sonnet 5.5's rank as an ordinal, and the sidecar's engine.
    engine = _engine_upgrade()["engine_version"].removeprefix("policyengine-us ")
    ordinal = ORDINALS[facts["sonnetRank"]]
    assert note["title"] == (
        f"Claude Sonnet 5.5 debuts {ordinal} as the references move to "
        f"policyengine-us {engine}"
    )
    assert note["slug"] == f"{note['date']}-claude-sonnet-5-5-debuts-{ordinal}"
    assert facts["engineVersion"] == engine
    assert (
        _release_20260929_tag()
        == note["release"]
        == "dashboard-data-" + (note["date"].replace("-", ""))
    )
    ranked = sorted(rows, key=lambda row: -row["exact"])
    assert [row["model"] for row in ranked[:5]] == [
        "gpt-6-sol",
        "claude-opus-5.5",
        "gpt-5.6-sol",
        "gpt-6-luna",
        "claude-sonnet-5.5",
    ]
    # "About level": GPT-6 Luna leads Claude Sonnet 5.5 by under 0.1 points.
    assert 0 < by_model["gpt-6-luna"]["exact"] - by_model["claude-sonnet-5.5"]["exact"]
    assert (
        by_model["gpt-6-luna"]["exact"] - by_model["claude-sonnet-5.5"]["exact"] < 0.1
    )
    pin(
        "Claude Sonnet 5.5, Grok 4.7 and DeepSeek V4.1 Flash joined the board on "
        "2026-09-29, bringing it to {nModels} models.",
        "Claude Sonnet 5.5 scores {sonnetExact}% of answers within $1, weighted by "
        "household impact, #{sonnetRank} of {nModels}.",
        "GPT-6 Luna, #{lunaRank}, also rounds to {lunaExact}% and sits about level "
        "with it, less than {lunaSonnetGapBelow} points ahead.",
        "Grok 4.7 scores {grokExact}% (#{grokRank}) and DeepSeek V4.1 Flash "
        "{flashExact}% (#{flashRank}).",
        # The previous release's leader, recomputed on its references.
        "GPT-6 Sol still leads at {solExact}%, ahead of Claude Opus 5.5 "
        "({opusExact}%) and GPT-5.6 Sol ({sol56Exact}%).",
    )
    # "Still": release 20260922c published GPT-6 Sol first too.
    assert max(previous, key=previous.get) == "gpt-6-sol"

    # DeepSeek V4.1 Flash is priced at the standard (peak) list rate the
    # pricing page gives, wherever in the day its requests landed.
    from policybench.config import PRICE_OVERRIDES_PER_1M

    assert PRICE_OVERRIDES_PER_1M["deepseek-v4.1-flash"] == {
        "input": 0.30,
        "output": 1.20,
        "cache_read": 0.006,
    }
    config_source = re.sub(
        r"\s*#\s*", " ", (ROOT / "policybench/config.py").read_text()
    )
    assert "The row is priced at the peak list rate whenever the run happens" in (
        config_source
    )
    pin(
        "Claude Sonnet 5.5 costs ${sonnetCost} a household, against ${lunaCost} "
        "for GPT-6 Luna.",
        "DeepSeek V4.1 Flash costs ${flashCost} at DeepSeek's peak list "
        "price, and Grok 4.7 costs ${grokCost}.",
    )

    # Serving: the frozen configuration and the model cards' onboarding notes.
    serving = _load_json(_at_20260929(SERVING_CONFIG_PATH))["models"]
    for model in ("claude-sonnet-5.5", "claude-opus-5.5", "claude-fable-5.1"):
        assert serving[model]["answer_contract"] == "json"
        assert serving[model]["tool_choice"] is None
    sonnet_card = MODEL_CARDS["claude-sonnet-5-5"].notes
    assert "rejects forced tool use" in sonnet_card
    assert "as on Opus 5.5 and Fable 5.1" in sonnet_card
    assert "provider default (adaptive thinking" in sonnet_card
    assert serving["claude-sonnet-5.5"]["evidence"]["treatment_fingerprint"][
        "thinking"
    ] == {"mode": "provider_default"}
    assert serving["grok-4.7"]["answer_contract"] == "tool"
    assert serving["grok-4.7"]["tool_choice"] == "forced"
    assert "timed out on the whole-scenario probe" in MODEL_CARDS["xai/grok-4.7"].notes
    flash = _added_model_responses()["deepseek-v4.1-flash"]
    assert serving["deepseek-v4.1-flash"]["provider_id"] == "deepseek/deepseek-flash"
    assert flash["resolved"] == {"deepseek-flash"}
    assert len(flash["fingerprints"]) == 1 and "" not in flash["fingerprints"]
    assert MODEL_RELEASE_DATES["deepseek-v4.1-flash"] == "2026-09-10"
    registry = (ROOT / "policybench/paper_results.py").read_text()
    assert "api-docs.deepseek.com/news/news260910" in registry
    assert "live on the API as deepseek-flash" in registry
    pin(
        "Claude Sonnet 5.5's API rejects forced tool calls, as Claude Opus 5.5's "
        "and Claude Fable 5.1's do, so its row answers as a JSON object and "
        "reasons with adaptive thinking, the provider default.",
        "Grok 4.7 answers through the forced tool call with a "
        "{grokTimeoutSeconds}-second request timeout, because its whole-household "
        "onboarding probe ran past a {grokOnboardingTimeoutSeconds}-second timeout.",
        "DeepSeek serves V4.1 Flash under the alias deepseek-flash, and all "
        "{flashAnswers} of the row's answers report that alias and one system "
        "fingerprint; none reports a version.",
        "PolicyBench labels the row from DeepSeek's September 10 release note, "
        "which put V4.1 Flash on that alias.",
    )

    # The engine move, as the upgrade record states it, with each release's
    # PyPI upload time, and the check on the newest release when PolicyBench
    # read PyPI before publishing.
    readme = re.sub(r"\s+", " ", UPGRADE_README.read_text())
    check = facts["checkEngine"]
    assert (
        f"policyengine-us {engine}, the newest release when PolicyBench began "
        "sweeping the references on 2026-09-29 (uploaded "
        f"{facts['engineUploadedUtc']} UTC)"
    ) in readme
    assert (
        f"policyengine-us {check}, the newest release when PolicyBench checked "
        f"PyPI on {PYPI_READ_AT_UTC[:10]} at {facts['checkPypiReadUtc']} UTC, gives "
        f"the same value as {engine} for all {facts['totalOutputs']:,} outputs"
    ) in readme
    assert "are all in 2.15.17 and need no module" in readme
    assert "The nine publication conventions" in readme
    assert facts["conventions"] == 9
    manifest = _load_json(_at_20260929(SNAPSHOT_DIR / "manifest.json"))
    refresh = manifest["reference_output_refresh"]
    assert refresh["policyengine_us_version"] == facts["engineVersion"]
    # PolicyBench began sweeping on the day it rebuilt the references.
    assert refresh["regenerated_at_utc"][:10] == "2026-09-29"
    # The freeze the conventions hold: the references' first generation, and
    # the date the upgrade's rule names.
    assert refresh["generated_at_utc"][:10] == "2026-07-03"
    assert (
        "law published before the 2026-07-03 reference freeze"
        in (_engine_upgrade()["rule"])
    )
    # The check ran the conventions plus the Maryland output-scope adapter.
    with PUBLICATION_CHECK_PATH.open(encoding="utf-8", newline="") as source:
        assert {row["fix"] for row in csv.DictReader(source)} == {"latest_final"}
    final_module = (
        ROOT / "reference_audit/2026-09-28/fixes/latest_final.py"
    ).read_text()
    assert (
        'PARTS = ("latest_conventions", "latest_md_local_output_scope")' in final_module
    )
    assert "keeps Maryland county\nincome tax out of the state income tax output" in (
        final_module
    )
    pin(
        "The release also moves PolicyBench's scored references from "
        "policyengine-us {previousEngine} to {engineVersion}, the newest release "
        "when PolicyBench began sweeping the references on 2026-09-29 (uploaded "
        "at {engineUploadedUtc} UTC).",
        "The newer version includes the {upstreamFixed:words} upstream fixes that "
        "PolicyBench applied as sandbox fixes for the September 22 references, and "
        "it encodes law the older version lacked.",
        "PolicyBench still builds each scored reference from the stated facts and "
        "law published before it froze the references on 2026-07-03, so it ported "
        "its {conventions:words} publication conventions to the new version.",
        "With those conventions and an adapter that keeps Maryland county tax out "
        "of state income tax, policyengine-us {checkEngine}, the newest release "
        f"when PolicyBench checked PyPI on {PYPI_READ_AT_UTC[:10]} at "
        "{checkPypiReadUtc} UTC, gives the same value as {engineVersion} for all "
        "{totalOutputs} outputs.",
    )

    # The four scored changes, each with the basis the sidecar records.
    changes = {
        state: next(
            c
            for c in _engine_upgrade()["changed"]
            if (c["scenario_id"], c["variable"]) == key
        )
        for state, key in UPGRADE_CHANGES.items()
    }
    payload = _dashboard_20260929()
    for state, (scenario_id, _) in UPGRADE_CHANGES.items():
        assert payload["scenarios"][scenario_id]["state"] == state
    assert (
        "2026-2028 (P.L.2026, c.26, approved June 30, 2026)" in (changes["NJ"]["basis"])
    )
    assert "7 CFR 245.6(a)(5)(ii)" in changes["PA"]["basis"]
    assert (
        "Child support received counts as household income" in (changes["PA"]["basis"])
    )
    assert (
        "policyengine-us added it to the school-meal income sources"
        in (changes["PA"]["basis"])
    )
    assert (changes["PA"]["previous"], changes["PA"]["regenerated"]) == (1.0, 0.0)
    assert "Empire State child credit phase-out rounding" in changes["NY"]["basis"]
    assert "policyengine-us#9425" in changes["NY"]["basis"]
    pin(
        "The move changes {scoredChanges:words} scored references.",
        "New Jersey's child tax credit schedule for 2026 to 2028, which the state "
        "approved on June 30, raises one household's state refundable credits from "
        "${njBefore} to ${njAfter}.",
        "Arizona raised the income limit for its broad-based categorical "
        "eligibility from {azLimitBefore}% to {azLimitAfter}% of the poverty "
        "guideline effective March, and the new limit gives an Arizona household "
        "${azAfter} of SNAP where the reference was ${azBefore}.",
        "policyengine-us now counts child support received as school-meal income, "
        "which ends a Pennsylvania household's eligibility for reduced-price meals.",
        "A fix to the rounding in New York's Empire State child credit phase-out "
        "(policyengine-us #9425) raises a New York household's state refundable "
        "credits from ${nyBefore} to ${nyAfter}.",
    )

    # The new exclusions: federal income tax, the SALT refund reading. The
    # engine revision lists them; the one other exclusion decided that day is
    # the audit's (final_actions.json audit_exclusions), which it does not.
    revised = {(c["scenario_id"], c["variable"]) for c in _engine_upgrade()["changed"]}
    decided = [
        e
        for e in _load_json(_at_20260929(EXCLUSIONS_PATH))["exclusions"]
        if e["decided_on"] == note["date"]
    ]
    new = [e for e in decided if (e["scenario_id"], e["variable"]) in revised]
    (medicaid,) = [
        e for e in decided if (e["scenario_id"], e["variable"]) not in revised
    ]
    assert len(new) == facts["newExclusions"]
    # Every rechecked output is excluded, and its value moved on the new engine.
    excluded_keys = {
        (e["scenario_id"], e["variable"])
        for e in _load_json(_at_20260929(EXCLUSIONS_PATH))["exclusions"]
    }
    for record in _engine_upgrade()["excluded_outputs_rechecked"]:
        assert (record["scenario_id"], record["variable"]) in excluded_keys
        assert record["value_on_2_15_17"] != record["kept_value"]
    for exclusion in new:
        assert exclusion["variable"] == "federal_income_tax_before_refundable_credits"
        assert exclusion["reason_code"] == "reference_depends_on_unlisted_input"
        assert (
            "counts the whole refund in gross income"
            in (exclusion["alternative_reading"])
        )
        assert "26 U.S.C. 111(a)" in exclusion["alternative_reading"]
    # The audit's exclusion: the California household head's Medicaid
    # eligibility turns on the same unlisted input as the household's SNAP,
    # which the upgrade re-reviewed; the probe computed both readings.
    assert (medicaid["scenario_id"], medicaid["variable"]) == MEDICAID_EXCLUSION
    assert payload["scenarios"][MEDICAID_EXCLUSION[0]]["state"] == "CA"
    assert medicaid["reason_code"] == "reference_depends_on_unlisted_input"
    snap_exclusion = next(
        e
        for e in _load_json(_at_20260929(EXCLUSIONS_PATH))["exclusions"]
        if (e["scenario_id"], e["variable"]) == (MEDICAID_EXCLUSION[0], "snap")
    )
    assert (
        medicaid["unlisted_input"]
        == snap_exclusion["unlisted_input"]
        == "meets_ssi_disability_criteria"
    )
    assert any(
        (r["scenario_id"], r["variable"]) == (MEDICAID_EXCLUSION[0], "snap")
        for r in _engine_upgrade()["excluded_outputs_rechecked"]
    )
    (audit,) = _load_json(UPGRADE_ACTIONS)["audit_exclusions"]
    assert audit["flagged_by"] == "excl_snap_ssi_disability"
    assert audit["exclusion"] == medicaid
    assert "42 CFR 435.540(a)" in medicaid["alternative_reading"]
    assert "Working Disabled Program" in medicaid["alternative_reading"]
    assert "tests the broad is_disabled flag instead" in medicaid["alternative_reading"]
    probe = _load_json(MEDICAID_PROBE_PATH)["results"]
    assert (medicaid["frozen_value"], medicaid["alternative_value"]) == (1.0, 0.0)
    assert probe["latest_final/stated_facts"]["head_medicaid_eligible"] == 1.0
    assert probe["latest_final_wdp_ssa_definition/reading_a"][
        "head_medicaid_eligible"
    ] == (0.0)
    assert probe["latest_final_wdp_ssa_definition/reading_b"][
        "head_medicaid_eligible"
    ] == (1.0)
    # The head's only disability fact is the general flag.
    head = _person(
        _scenario_inputs(_at_20260929(RUN_DIR))[MEDICAID_EXCLUSION[0]], "head"
    )
    assert head["is_disabled"] is True
    assert not {k for k in head if "disab" in k or "ssi" in k} - {"is_disabled"}
    pin(
        "PolicyBench stops scoring {newExclusions:words} federal income tax outputs.",
        "policyengine-us {engineVersion} counts the whole of a listed state and "
        "local tax refund as income.",
        "Federal law counts the refund only to the extent the refunded tax lowered "
        "the household's federal tax in the year the household paid it, and the "
        "prompts do not say whether it did.",
        "PolicyBench also stops scoring one California household head's Medicaid "
        "eligibility, which its re-review of the household's excluded SNAP output "
        "flagged.",
        "On disability, the prompt says only that the head is disabled.",
        "The head's income, {medicaidIncomePercent}% of the poverty guideline, is "
        "above the {expansionLimitPercent}% limit for the adult expansion group, so "
        "only a disability pathway leads to Medi-Cal, California's Medicaid program.",
        "Medi-Cal's Working Disabled Program requires SSI's definition of "
        "disability, which the prompt does not state, and "
        "policyengine-us {engineVersion} tests the general disability flag instead.",
        "The same unstated fact already keeps the household's SNAP out of scoring.",
        "PolicyBench now scores every model on {scoredOutputs} of its "
        "{totalOutputs} requested outputs and excludes {excluded}.",
        "Another {withinTolerance:words} references move by less than $1, and "
        "PolicyBench re-reviewed the {rechecked} excluded outputs whose values "
        "moved; all stay excluded.",
    )

    # The incumbents' drift: every score rises, no one matched the federal
    # outputs now excluded, and every one matched Arizona's old reference.
    incumbents = sorted(previous)
    after = {m: by_model[m]["exact"] for m in incumbents}
    assert all(after[m] > previous[m] for m in incumbents)
    # The rise is the two causes' joint effect: the Medicaid exclusion by
    # itself lowers the rate of every incumbent that had matched that output,
    # so the note says "Together".
    medicaid_answers = payload["scenarioPredictions"][MEDICAID_EXCLUSION[0]][
        MEDICAID_EXCLUSION[1]
    ]
    medicaid_matched = [
        m
        for m in incumbents
        if medicaid_answers[m].get("prediction") == medicaid["frozen_value"]
    ]
    assert len(medicaid_matched) == facts["medicaidMatched"]
    medicaid_scored = _exact_under(False, score_audit_exclusions=True)
    assert all(after[m] < medicaid_scored[m] for m in medicaid_matched)
    for exclusion in new:
        key = (exclusion["scenario_id"], exclusion["variable"])
        previous = next(
            c["previous"]
            for c in _engine_upgrade()["changed"]
            if (c["scenario_id"], c["variable"]) == key
        )
        entries = payload["scenarioPredictions"][key[0]][key[1]]
        assert not any(
            _matches(entries[m].get("prediction"), previous) for m in incumbents
        )
    arizona = payload["scenarioPredictions"]["scenario_013"]["snap"]
    assert all(
        _matches(arizona[m].get("prediction"), changes["AZ"]["previous"])
        for m in incumbents
    )
    assert not any(
        _matches(arizona[m].get("prediction"), changes["AZ"]["regenerated"])
        for m in by_model
    )
    # The drift's two causes, as the drift baseline test rebuilds them.
    test_previous_release_scores_rebuild_from_this_snapshot()
    pin(
        "Together, the new references and the Medicaid exclusion raise the exact "
        "rate of every one of the {incumbents} earlier models, by {driftMin} to "
        "{driftMax} points.",
        "None of the {incumbents} matched any of the {newExclusions:words} federal "
        "outputs now excluded, and all {incumbents} had matched the Arizona "
        "household's old ${azBefore} SNAP reference, which none matches now.",
        "On the Medicaid output, {medicaidMatched} of the {incumbents} had matched "
        "the reference and {medicaidMissed} had not.",
        "Among the {incumbents}, {riserCount:words} models move up in the order: "
        "{riserOne} moves above {riserOnePassed}, {riserTwo} above "
        "{riserTwoPassed}, {riserThree} above {riserThreePassed}, {riserFour} "
        "above {riserFourPassed}, and {riserFive} above {riserFivePassed}.",
        "Every other pair keeps its order.",
    )

    # The Arizona household in the BBCE note's terms: it qualifies only through
    # BBCE (the upgrade's investigation), and every model answers $0.
    clusters = _load_json(UPGRADE_CLUSTERS)
    cluster = next(
        c
        for c in (clusters["clusters"] if "clusters" in clusters else clusters.values())
        if isinstance(c, dict) and c.get("id") == "az_snap_bbce_200"
    )
    summary = cluster["investigation"]["summary"]
    assert "fails the net-income test" in summary and "it is ECE from March" in summary
    assert all(arizona[m].get("prediction") == 0 for m in by_model)
    # The October 5 BBCE note counts the Arizona household as a fifth held
    # back by income, beside the four in the states this note names, and its
    # data files give every model's answers, the three added models' among
    # them, for those five and for the households held back by savings.
    bbce = _note(BBCE_NOTE)
    assert bbce["date"] == "2026-10-05"
    assert f"/notes/{RELEASE_NOTE}" in {entry["href"] for entry in bbce["data"]}
    bbce_income = _load_json(BBCE_ROWS_META_PATH)["households"]
    bbce_savings = _load_json(BBCE_ASSET_ROWS_META_PATH)["households"]
    assert UPGRADE_CHANGES["AZ"][0] in bbce_income
    assert (
        len(bbce_income)
        == bbce["facts"]["householdCount"]
        == (facts["bbceIncomeHeldCount"] + 1)
    )
    assert (
        len(bbce_savings)
        == bbce["facts"]["assetOnlyCount"]
        == (facts["bbceAssetHeldCount"])
    )
    assert sorted(
        STATE_NAMES[_dashboard_20260929()["scenarios"][s]["state"]]
        for s in bbce_income
        if s != UPGRADE_CHANGES["AZ"][0]
    ) == sorted(facts["bbceIncomeHeldStates"].replace(" and ", ", ").split(", "))
    for path, households in (
        (BBCE_ROWS_PATH, bbce_income),
        (BBCE_ASSET_ROWS_PATH, bbce_savings),
    ):
        answered = {(row["model"], row["scenario_id"]) for row in _read_csv(path)}
        assert {(m, s) for m in by_model for s in households} <= answered
    pin(
        "The Arizona household's income keeps it from qualifying for SNAP under "
        "the program's ordinary tests, so it qualifies only through broad-based "
        "categorical eligibility, and all {nModels} models answer $0 for it.",
        "PolicyBench's October 5 note on such households counts it among five "
        "held back by income, with {bbceIncomeHeldCount:words} in "
        "{bbceIncomeHeldStates}.",
        "That note's data list every model's answer for those five households "
        "and for the {bbceAssetHeldCount:words} held back by savings, including "
        "the three models this release adds.",
    )

    # The models the prose names, and no sentence left unpinned.
    assert _named_models(text, display) >= {
        "claude-sonnet-5.5",
        "grok-4.7",
        "deepseek-v4.1-flash",
        "gpt-6-luna",
        "gpt-6-sol",
        "claude-opus-5.5",
        "gpt-5.6-sol",
        "claude-fable-5.1",
    }
    unpinned = text
    for sentence in pinned:
        unpinned = unpinned.replace(sentence, "", 1)
    assert not unpinned.strip(), unpinned

    links = {entry["label"]: entry["href"] for entry in note["data"]}
    assert links["Dashboard data release"].endswith("/tag/" + note["release"])
    assert links["Claude Sonnet 5.5 model page"] == "/model/claude-sonnet-5.5"
    assert links["Grok 4.7 model page"] == "/model/grok-4.7"
    assert links["DeepSeek V4.1 Flash model page"] == "/model/deepseek-v4.1-flash"


def test_previous_release_scores_rebuild_from_this_snapshot() -> None:
    """The drift baseline is the previous release's own board. Every model's
    exact score, rebuilt from release 20260929's predictions (its commit's
    snapshot) with the upgrade and the audit exclusion reverted, equals the
    score release dashboard-data-20260922c published (the committed fixture of
    its asset's scores); the current scores rebuild to release 20260929's
    payload. So the note's drift comes from the reference revision and the
    audit exclusion alone."""
    after = _exact_under(False)
    for row in _board_rows():
        assert after[row["model"]] == pytest.approx(row["exact"], abs=1e-9)
    before = _exact_under(True)
    previous = _previous_release_scores()
    assert set(previous) == set(before) - set(ADDED_MODELS)
    for model, exact in previous.items():
        assert before[model] == pytest.approx(exact, abs=1e-9), model


BBCE_UPDATE_RELEASE = "dashboard-data-20260929"


def test_bbce_rows_20260929_regenerate() -> None:
    """The BBCE rows on release dashboard-data-20260929, which the September
    29 release note's facts count, regenerate from that release's payload as
    its commit holds it, with the mention patterns their metas record, and
    the metas pin that release."""
    sys.path.insert(0, str(ROOT / "scripts"))
    from bbce_households_20260929 import (
        ASSET_HOUSEHOLDS,
        INCOME_HOUSEHOLDS,
        build,
        meta_path,
    )

    assert _release_20260929_tag() == BBCE_UPDATE_RELEASE
    payload = _dashboard_20260929()
    board = sorted(row["model"] for row in _board_rows())
    manifest = _load_json(_at_20260929(SNAPSHOT_DIR / "manifest.json"))
    built = build(payload)
    assert [households for _, households, _ in built.values()] == [
        INCOME_HOUSEHOLDS,
        ASSET_HOUSEHOLDS,
    ]
    for output, (rows, households, patterns) in built.items():
        assert _read_csv(output) == [
            {key: str(value) for key, value in row.items()} for row in rows
        ]
        meta = _load_json(meta_path(output))
        assert meta["release"] == BBCE_UPDATE_RELEASE
        assert meta["households"] == households
        assert meta["mention_patterns"] == patterns
        assert meta["rows"] == len(rows) == len(board) * len(households)
        assert meta["run_payload_sha256"] == _sha256_file(
            run_payload_path(_at_20260929(RUN_DIR))
        )
        assert (
            meta["release_payload_sha256"]
            == manifest["published_dashboard_artifact"]["sha256"]
        )


# ----- Release dashboard-data-20261006 --------------------------------------

RELEASE_20261006 = "dashboard-data-20261006"
EXCLUSIONS_NOTE = "2026-10-06-policybench-stops-scoring-eight-tax-outputs"
# The rulings of 2026-10-05 the release applies, and the audits behind them.
RELEASE_20261006_SPEC = ROOT / "docs/release_20261006/spec.json"
SALT_AUDIT = ROOT / "reference_audit/2026-10-05"
PART_B_AUDIT = ROOT / "reference_audit/2026-10-05-medicare-part-b"
PAYROLL_AUDIT = ROOT / "reference_audit/2026-10-05-payroll"
MEDICAID_031_AUDIT = ROOT / "reference_audit/2026-10-05-medicaid-031-annotations"
FEDERAL_INCOME_TAX = "federal_income_tax_before_refundable_credits"
STATE_INCOME_TAX = "state_income_tax_before_refundable_credits"
# The unlisted inputs the eight records name, by the words they open with.
SALT_INPUT = "state income tax withheld or paid during 2026"
PART_B_INPUT = "Medicare enrollment and a Medicare Part B premium paid during 2026"
PAYROLL_INPUT = (
    "whether the employer deducts the employee share of a state paid-leave or "
    "disability premium that the law lets it deduct but does not require"
)
# The words NotesContent.tsx renders for a `{key:words}` placeholder.
NUMBER_WORDS = (
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
)


def _no_tools_exact(payload: dict) -> dict[str, float]:
    return {
        row["model"]: row["exact"]
        for row in payload["modelStats"]
        if row["condition"] == "no_tools"
    }


def _new_exclusions() -> list[dict]:
    """The records release 20261006 adds to release 20260930's, in the
    record's order. Every earlier record is kept."""
    then = _load_json(_in(_release_root(RELEASE_20260930), EXCLUSIONS_PATH))
    now = _load_json(_in(_release_root(RELEASE_20261006), EXCLUSIONS_PATH))
    earlier = {(e["scenario_id"], e["variable"]) for e in then["exclusions"]}
    assert earlier <= {(e["scenario_id"], e["variable"]) for e in now["exclusions"]}
    return [
        e for e in now["exclusions"] if (e["scenario_id"], e["variable"]) not in earlier
    ]


def _readme(path: Path) -> str:
    return re.sub(r"\s+", " ", (path / "README.md").read_text())


def _list_with_and(items: list[str]) -> str:
    """Items joined with a serial comma, as the October 6 note writes lists."""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + ", and " + items[-1]


def _release_20261006_facts() -> dict:
    """The October 6 release note's facts, recomputed from release 20261006's
    snapshot and records, and from release 20260930's at its commit."""
    from policybench.paper_results import MODEL_DISPLAY_NAMES

    now_root = _release_root(RELEASE_20261006)
    then_root = _release_root(RELEASE_20260930)
    now, then = _payload_at(now_root), _payload_at(then_root)
    new = _new_exclusions()
    by_key = {(e["scenario_id"], e["variable"]): e for e in new}
    states = {
        e["scenario_id"]: now["scenarios"][e["scenario_id"]]["state"] for e in new
    }
    federal = [e for e in new if e["variable"] == FEDERAL_INCOME_TAX]
    state_tax = [e for e in new if e["variable"] == STATE_INCOME_TAX]
    payroll = [e for e in new if e["variable"] == "payroll_tax"]
    assert len(federal) + len(state_tax) + len(payroll) == len(new)

    def cents(value: float) -> int | str:
        return _whole_or_cents(round(value, 2))

    def matches(record: dict, value: float) -> list[str]:
        cell = now["scenarioPredictions"][record["scenario_id"]][record["variable"]]
        return sorted(
            m for m, e in cell.items() if _matches(e.get("prediction"), value)
        )

    board = [r for r in now["modelStats"] if r["condition"] == "no_tools"]
    previous_board = [r for r in then["modelStats"] if r["condition"] == "no_tools"]
    after, before = _no_tools_exact(now), _no_tools_exact(then)
    risers = _models_moving_up(before, after)
    exclusions = _load_json(_in(now_root, EXCLUSIONS_PATH))["exclusions"]
    classification = _load_json(PAYROLL_AUDIT / "program_classification.json")
    payroll_ids = {e["scenario_id"] for e in payroll}
    optional = [
        p
        for p in classification["programs"]
        if p["classification"] == "optional_employer_pass_through"
        and set(p["benchmark_outputs"]) & payroll_ids
    ]
    excluded_keys = {(e["scenario_id"], e["variable"]) for e in exclusions}
    mandatory = sorted(
        {
            scenario_id
            for p in classification["programs"]
            if p["classification"] == "mandatory_employee_withholding"
            for scenario_id in p["benchmark_outputs"]
            if (scenario_id, "payroll_tax") not in excluded_keys
        }
    )
    window = _load_json(_in(now_root, SNAPSHOT_DIR / "manifest.json"))[
        "model_response_date"
    ]
    previous_window = _load_json(_in(then_root, SNAPSHOT_DIR / "manifest.json"))[
        "model_response_date"
    ]
    start, end = window.split(" to ")
    previous_start, previous_end = previous_window.split(" to ")
    assert previous_start == start
    (engine,) = {e["engine_version"].removeprefix("policyengine-us ") for e in new}
    part_b = re.search(
        r"the 2026 standard premium of \$202\.90 a month, \$([\d,]+\.\d\d)",
        by_key[("scenario_114", STATE_INCOME_TAX)]["alternative_reading"],
    )
    assert part_b is not None
    engine_values = _load_json(MEDICAID_031_AUDIT / "verification/engine_values.json")
    parameters = engine_values["parameters"]
    derived = {
        "newExclusions": len(new),
        "newHouseholds": len(states),
        "scoredOutputs": board[0]["n"],
        "totalOutputs": sum(1 for _ in open(_in(now_root, REFERENCES_PATH))) - 1,
        "previousScoredOutputs": previous_board[0]["n"],
        "excluded": len(exclusions),
        "federalOutputs": len(federal),
        "engineVersion": engine,
        "va114Age": _person(
            _scenario_inputs(_in(now_root, RUN_DIR))["scenario_114"], "head"
        )["age"],
        "partBPremium": part_b.group(1),
        "payrollOutputs": len(payroll),
        "optionalPrograms": _list_with_and([p["program"] for p in optional]),
        "mandatoryScored": len(mandatory),
        "mandatoryStates": _list_with_and(
            sorted({STATE_NAMES[now["scenarios"][s]["state"]] for s in mandatory})
        ),
        "incomeTaxOutputs": len(federal) + len(state_tax),
        "payrollHits": sum(len(matches(e, e["frozen_value"])) for e in payroll),
        "payrollAltHits": sum(len(matches(e, e["alternative_value"])) for e in payroll),
        "riseMin": round(min(after[m] - before[m] for m in after), 2),
        "riseMax": round(max(after[m] - before[m] for m in after), 2),
        "solExact": _display_one_decimal(after["gpt-6-sol"]),
        "opusExact": _display_one_decimal(after["claude-opus-5.5"]),
        "sol56Exact": _display_one_decimal(after["gpt-5.6-sol"]),
        "sonnetExact": _display_one_decimal(after["claude-sonnet-5.5"]),
        "lunaExact": _display_one_decimal(after["gpt-6-luna"]),
        "responseStart": _month_day(start),
        "responseEnd": _month_day(end),
        "previousResponseEnd": _month_day(previous_end),
        "medicaidDisregard": int(
            parameters["senior_or_disabled.income.disregard.individual[CA] (monthly)"]
        ),
        "ssiExclusion": int(parameters["ssa.ssi.income.exclusions.general (monthly)"]),
    }
    for record in federal:
        number = record["scenario_id"].removeprefix("scenario_")
        derived[f"fed{number}Alt"] = cents(record["alternative_value"])
        derived[f"fed{number}Ref"] = cents(record["frozen_value"])
    (virginia,) = state_tax
    number = virginia["scenario_id"].removeprefix("scenario_")
    derived[f"va{number}Alt"] = cents(virginia["alternative_value"])
    derived[f"va{number}Ref"] = cents(virginia["frozen_value"])
    for record in payroll:
        state = states[record["scenario_id"]].lower()
        derived[f"{state}Alt"] = cents(record["alternative_value"])
        derived[f"{state}Ref"] = cents(record["frozen_value"])
        derived[f"{state}Hits"] = len(matches(record, record["frozen_value"]))
    # The first riser is Claude Sonnet 5.5, which the note names; the others
    # are named from the facts.
    (first, first_passed), *others = risers
    assert (first, first_passed) == ("claude-sonnet-5.5", ["gpt-6-luna"])
    for ordinal, (riser, passed) in zip(("Two", "Three", "Four"), others, strict=True):
        derived[f"riser{ordinal}"] = MODEL_DISPLAY_NAMES[riser]
        derived[f"riser{ordinal}Passed"] = _and(
            [MODEL_DISPLAY_NAMES[m] for m in passed]
        )
    return derived


def test_release_20261006_note() -> None:
    """The October 6 release note: its facts recompute from release 20261006's
    snapshot and records and from release 20260930's at its commit, every
    sentence is pinned beside the evidence for it, and every link resolves."""
    from policybench.paper_results import MODEL_DISPLAY_NAMES

    note = _note(EXCLUSIONS_NOTE)
    facts = note["facts"]
    assert note["release"] == RELEASE_20261006
    assert facts == _release_20261006_facts()
    text = " ".join(note["paragraphs"])
    pinned: list[str] = []

    def pin(*sentences: str) -> None:
        for sentence in sentences:
            assert text.count(sentence) == 1, sentence
            pinned.append(sentence)

    now_root = _release_root(RELEASE_20261006)
    then_root = _release_root(RELEASE_20260930)
    now, then = _payload_at(now_root), _payload_at(then_root)
    spec = _load_json(RELEASE_20261006_SPEC)
    new = _new_exclusions()
    by_key = {(e["scenario_id"], e["variable"]): e for e in new}
    states = {s: now["scenarios"][s]["state"] for s, _ in by_key}
    names = {s: STATE_NAMES[state] for s, state in states.items()}
    scenarios = _scenario_inputs(_in(now_root, RUN_DIR))

    # The release: the rulings' eight records, decided that day on the
    # references' engine, on the same references, predictions and board.
    assert spec["release_tag"] == note["release"]
    assert spec["base_tag"] == RELEASE_20260930
    assert spec["base_commit"] == RELEASE_20260930_COMMIT
    assert note["release"] == "dashboard-data-" + note["date"].replace("-", "")
    assert sorted(by_key) == sorted(
        tuple(output)
        for proposal in spec["proposals"]
        for output in proposal["outputs"]
    )
    reference_meta = _load_json(_in(now_root, REFERENCE_META_PATH))
    engine = reference_meta["policyengine_bundles"]["us"]["model_version"]
    for record in new:
        assert record["decided_on"] == spec["decided_on"]
        assert record["reason_code"] == "reference_depends_on_unlisted_input"
        assert record["engine_version"] == f"policyengine-us {engine}"
    for name in (REFERENCES_PATH, PREDICTIONS_PATH):
        assert _sha256_file(_in(now_root, name)) == _sha256_file(_in(then_root, name))
    assert set(_no_tools_exact(now)) == set(_no_tools_exact(then))
    for root in (now_root, then_root):
        manifest = _load_json(_in(root, SNAPSHOT_DIR / "manifest.json"))
        assert manifest["snapshot_date"] == note["boardSnapshot"]
    references = {
        (row["scenario_id"], row["variable"]): float(row["value"])
        for row in _read_csv(_in(now_root, REFERENCES_PATH))
    }
    for key, record in by_key.items():
        assert record["frozen_value"] == references[key]
        for entry in now["scenarioPredictions"][key[0]][key[1]].values():
            assert entry["groundTruth"] == record["frozen_value"]
            assert entry["scored"] is False
        for entry in then["scenarioPredictions"][key[0]][key[1]].values():
            assert entry["scored"] is True
    # The exclusion rule the records apply.
    rule = _load_json(_in(now_root, EXCLUSIONS_PATH))["rule"]
    assert rule.startswith(
        "An output is excluded from scoring for every model when its reference "
        "depends on an input or definition that the certified household data "
        "never carried and the prompt therefore never stated"
    )

    # Which outputs, in which households.
    federal = [k for k in by_key if k[1] == FEDERAL_INCOME_TAX]
    state_tax = [k for k in by_key if k[1] == STATE_INCOME_TAX]
    payroll = [k for k in by_key if k[1] == "payroll_tax"]
    federal_ids = [s for s, _ in sorted(federal)]
    payroll_ids = [s for s, _ in sorted(payroll)]
    assert [states[s] for s in federal_ids] == ["CA", "MA", "VA"]
    assert state_tax == [("scenario_114", STATE_INCOME_TAX)]
    assert states["scenario_114"] == "VA"
    shared = [s for s in payroll_ids if s in federal_ids]
    payroll_others = [names[s] for s in payroll_ids if s not in federal_ids]
    assert [names[s] for s in shared] == ["Massachusetts"]
    title_word = NUMBER_WORDS[facts["newExclusions"]]
    assert note["title"] == (
        f"PolicyBench stops scoring {title_word} tax outputs whose references turn "
        "on facts the prompts never state"
    )
    assert note["slug"] == (
        f"{note['date']}-policybench-stops-scoring-{title_word}-tax-outputs"
    )
    pin(
        "PolicyBench stops scoring {newExclusions:words} tax outputs, in "
        "{newHouseholds:words} households, whose references turn on facts the "
        "prompts never state.",
        "The {newExclusions:words} are federal income tax for households in "
        f"{_list_with_and([names[s] for s in federal_ids])}; the "
        f"{names['scenario_114']} household's state income tax; and payroll tax "
        f"for the {names[shared[0]]} household and households in "
        f"{_list_with_and(payroll_others)}.",
        "Every model is now scored on {scoredOutputs} of its {totalOutputs} "
        "requested outputs, down from {previousScoredOutputs}, and PolicyBench "
        "excludes {excluded}.",
    )
    assert facts["scoredOutputs"] + facts["excluded"] == facts["totalOutputs"]
    assert facts["previousScoredOutputs"] - facts["scoredOutputs"] == len(new)

    # The state income tax in SALT: the records, and the audit's statement
    # of the engine's mechanism and of the law.
    salt = _readme(SALT_AUDIT)
    assert (
        "These files hold for policyengine-us 2.15.17, the version that built the "
        "published references" in salt
    )
    assert (
        "Under 26 U.S.C. 164(a)(3) and (b)(5), a household deducts the state "
        "income tax it paid during the year"
    ) in salt
    for key in federal:
        record = by_key[key]
        state = names[key[0]]
        reading = record["alternative_reading"]
        assert record["unlisted_input"].startswith(SALT_INPUT)
        assert "a formula estimate on federal AGI" in record["unlisted_input"]
        assert reading.startswith(
            "The prompt lists no state income tax withheld or paid during 2026. "
        )
        assert (
            "The reference fills the state income tax part of the federal state "
            "and local tax deduction (26 U.S.C. 164(a)(3), (b)(5)) with "
            f"policyengine-us's formula estimate of {state} income tax withheld"
        ) in reading
        assert (
            f"Read as the household paying its 2026 {state} income tax during the "
            "year, the deduction takes that liability and the output is the "
            "alternative value."
        ) in reading
        assert "the household itemizes under both" in record["note"]
        for prompt in now["scenarios"][key[0]]["prompt"].values():
            assert not re.search(
                r"withh|income tax", _household_block(prompt), re.IGNORECASE
            )
    pin(
        "The {federalOutputs:words} federal outputs depend on the state income "
        "tax each household paid during 2026, which the federal deduction for "
        "state and local taxes counts and no prompt lists.",
        "policyengine-us {engineVersion}, which built the references, fills that "
        "amount with its own estimate of state income tax withheld, a formula on "
        "federal adjusted gross income.",
        "If each household paid its 2026 state income tax as the engine computes "
        "it, the outputs are ${fed022Alt} in California, ${fed081Alt} in "
        "Massachusetts, and ${fed114Alt} in Virginia, against references of "
        "${fed022Ref}, ${fed081Ref}, and ${fed114Ref}.",
    )
    assert [names[s] for s in federal_ids] == [
        "California",
        "Massachusetts",
        "Virginia",
    ]

    # The Medicare Part B premium in the Virginia household.
    virginia = by_key[("scenario_114", STATE_INCOME_TAX)]
    virginia_federal = by_key[("scenario_114", FEDERAL_INCOME_TAX)]
    head = _person(scenarios["scenario_114"], "head")
    assert head["age"] == facts["va114Age"] >= 65
    assert virginia["unlisted_input"].startswith(PART_B_INPUT)
    assert (
        "policyengine-us treats every Medicare-eligible person as enrolled"
        in virginia["unlisted_input"]
    )
    reading = virginia["alternative_reading"]
    assert reading.startswith(
        "The prompt lists no Medicare enrollment and no Medicare Part B premium"
    )
    assert (
        f"policyengine-us treats the head (age {head['age']}, so Medicare-eligible) "
        "as enrolled because takes_up_medicare_if_eligible defaults to true"
    ) in reading
    assert "The household itemizes" in reading
    assert (
        "Virginia's itemized deductions, which start from the federal itemized "
        "deductions (va_itemized_deductions), carry it too."
    ) in reading
    assert (
        f"Read with no Part B premium paid, the deduction falls by "
        f"${facts['partBPremium']} and the output is the alternative value."
    ) in reading
    # The premium is $202.90 a month for 2026, as the engine models it for
    # scenario_031's head too.
    assert facts["partBPremium"] == f"{12 * 202.90:,.2f}"
    medicaid_values = _load_json(MEDICAID_031_AUDIT / "verification/engine_values.json")
    assert (
        f"{medicaid_values['readings']['modeled']['medicare_part_b_premium']:,.2f}"
        == facts["partBPremium"]
    )
    # Without the premium, both tax outputs are higher, and the federal
    # record names the premium beside the state income tax in SALT.
    assert virginia["alternative_value"] > virginia["frozen_value"]
    assert virginia_federal["unlisted_input"].startswith(SALT_INPUT)
    assert "; also " + PART_B_INPUT in virginia_federal["unlisted_input"]
    without_premium = re.search(
        r"Without it the output is \$([\d,]+\.\d\d) under the withholding estimate",
        virginia_federal["note"],
    )
    assert without_premium is not None
    assert (
        float(without_premium.group(1).replace(",", ""))
        > (virginia_federal["frozen_value"])
    )
    for prompt in now["scenarios"]["scenario_114"]["prompt"].values():
        assert not re.search(
            r"medicare|part b|premium", _household_block(prompt), re.IGNORECASE
        )
    pin(
        "The Virginia household's head is {va114Age}, and the prompt lists no "
        "Medicare enrollment or premium.",
        "policyengine-us treats everyone eligible for Medicare as enrolled and "
        "counts the standard Part B premium, ${partBPremium} for 2026, as a "
        "medical expense.",
        "The household itemizes, and Virginia's itemized deductions start from "
        "the federal ones, so the premium lowers its Virginia income tax: without "
        "it, that output is ${va114Alt} rather than the reference's ${va114Ref}.",
        "The premium lowers the household's federal income tax too, and that "
        "output's exclusion record names both unstated facts.",
    )

    # The payroll outputs: the programs, classified from primary law, and the
    # records' readings.
    classification = _load_json(PAYROLL_AUDIT / "program_classification.json")
    assert classification["test"].startswith(
        "Who owes the contribution under the statute. "
        "mandatory_employee_withholding: the statute puts the contribution on the "
        "worker and requires the employer to withhold it."
    )
    payroll_readme = _readme(PAYROLL_AUDIT)
    assert (
        "find that the premium is the employer's and that the law requires no "
        "amount of the employee: the employee pays only what the employer chooses "
        "to deduct, from $0 up to a cap. The frozen references count the cap."
    ) in payroll_readme
    optional = [
        p
        for p in classification["programs"]
        if p["classification"] == "optional_employer_pass_through"
        and set(p["benchmark_outputs"]) & set(payroll_ids)
    ]
    assert sorted(s for p in optional for s in p["benchmark_outputs"]) == payroll_ids
    assert [p["key"] for p in optional] == [states[s] for s in payroll_ids]
    payroll_line = (
        "- payroll_tax: annual household employee-side payroll tax: employee "
        "Social Security tax, employee Medicare tax, Additional Medicare Tax, and "
        "mandatory employee state payroll taxes."
    )
    for key in payroll:
        record = by_key[key]
        assert record["unlisted_input"] == PAYROLL_INPUT + (
            ", which decides whether that share is a mandatory employee state "
            "payroll tax"
        )
        # Massachusetts's record names the published rates: a literal reading
        # of Acts 2026 c. 101 would let the employer deduct more in 2026
        # (reference_audit/2026-10-05-payroll/README.md).
        largest = (
            "counts the largest share Massachusetts's published 2026 rates let "
            "the employer deduct"
            if key[0] == "scenario_081"
            else "counts the largest share the employer may deduct"
        )
        assert largest in record["alternative_reading"]
        assert (
            "Read as the amount the law requires of the employee whatever the "
            "employer does, which is $0, the output is employee federal payroll "
            "tax alone: the alternative value"
        ) in record["alternative_reading"]
        for prompt in now["scenarios"][key[0]]["prompt"].values():
            assert payroll_line in prompt
    # The payroll outputs PolicyBench still scores with a state contribution
    # the law requires of the worker; New Jersey's is excluded for an engine
    # defect.
    excluded_keys = {
        (e["scenario_id"], e["variable"])
        for e in _load_json(_in(now_root, EXCLUSIONS_PATH))["exclusions"]
    }
    mandatory = [
        p
        for p in classification["programs"]
        if p["classification"] == "mandatory_employee_withholding"
    ]
    unscored = [
        s
        for p in mandatory
        for s in p["benchmark_outputs"]
        if (s, "payroll_tax") in excluded_keys
    ]
    assert unscored == ["scenario_008"]
    assert now["scenarios"]["scenario_008"]["state"] == "NJ"
    pin(
        "The {payrollOutputs:words} payroll outputs count an employee share of a "
        "state paid-leave or disability premium: {optionalPrograms}.",
        "In each of these states the premium is the employer's, and the employer "
        "may deduct up to a set share of it from wages but need not, so the law "
        "requires no amount of the employee.",
        "The prompts ask for mandatory employee state payroll taxes, and the "
        "references count the largest share each state's published 2026 rates let "
        "the employer deduct, without the prompts saying whether it does.",
        "Without that share, the outputs are ${mnAlt} in Minnesota, ${coAlt} in "
        "Colorado, ${maAlt} in Massachusetts, and ${nyAlt} in New York, against "
        "references of ${mnRef}, ${coRef}, ${maRef}, and ${nyRef}.",
        "PolicyBench still scores the payroll outputs of {mandatoryScored:words} "
        "households in {mandatoryStates}, where the law puts the contribution on "
        "the worker and requires the employer to withhold it.",
    )
    assert [names[s] for s in payroll_ids] == [
        "Minnesota",
        "Colorado",
        "Massachusetts",
        "New York",
    ]

    # The answers on the eight outputs. A model's answer matches within $1,
    # the payload's own exact score.
    for key, record in by_key.items():
        cell = now["scenarioPredictions"][key[0]][key[1]]
        assert len(cell) == len(_no_tools_exact(now))
        frozen = {
            m
            for m, e in cell.items()
            if _matches(e.get("prediction"), record["frozen_value"])
        }
        alternative = {
            m
            for m, e in cell.items()
            if _matches(e.get("prediction"), record["alternative_value"])
        }
        assert frozen == {m for m, e in cell.items() if e["exact"] == 100}
        assert not frozen & alternative
        if key[1] != "payroll_tax":
            assert not frozen, key
    pin(
        "No model's answer is within $1 of the reference on any of the "
        "{incomeTaxOutputs:words} income tax outputs.",
        "On the {payrollOutputs:words} payroll outputs, {payrollHits} answers match "
        "the reference within $1: {mnHits:words} for Minnesota, {coHits} for "
        "Colorado, {maHits:words} for Massachusetts, and {nyHits:words} for New "
        "York.",
        "Another {payrollAltHits} match the amount without the state share.",
    )
    assert facts["payrollHits"] == sum(
        facts[f"{states[s].lower()}Hits"] for s in payroll_ids
    )

    # The board: every model rises; the order at the top, and every pair whose
    # order changes.
    after, before = _no_tools_exact(now), _no_tools_exact(then)
    board = [r for r in now["modelStats"] if r["condition"] == "no_tools"]
    previous_board = [r for r in then["modelStats"] if r["condition"] == "no_tools"]
    assert all(after[m] > before[m] for m in after)

    def rank_now(model: str) -> int:
        return _rank(after[model], board)

    def rank_then(model: str) -> int:
        return _rank(before[model], previous_board)

    for model, place in (("gpt-6-sol", 1), ("claude-opus-5.5", 2), ("gpt-5.6-sol", 3)):
        assert rank_now(model) == rank_then(model) == place
    assert (rank_then("gpt-6-luna"), rank_then("claude-sonnet-5.5")) == (4, 5)
    assert (rank_now("claude-sonnet-5.5"), rank_now("gpt-6-luna")) == (4, 5)
    assert ORDINALS[rank_now("claude-sonnet-5.5")] == "fourth"
    risers = _models_moving_up(before, after)
    assert len(risers) == 4
    for riser, passed in risers:
        # Each riser passes one model, the one just above it before.
        assert len(passed) == 1
        assert rank_now(riser) == rank_then(passed[0])
        assert rank_now(passed[0]) == rank_then(riser)
    pin(
        # The headline the board ranks by, as the September 29 note states it.
        "Every model's exact rate, its share of answers within $1 weighted by "
        "household impact, rises by {riseMin} to {riseMax} points.",
        "GPT-6 Sol still leads at {solExact}%, ahead of Claude Opus 5.5 "
        "({opusExact}%) and GPT-5.6 Sol ({sol56Exact}%).",
        "Claude Sonnet 5.5 ({sonnetExact}%) passes GPT-6 Luna ({lunaExact}%) for "
        "fourth.",
        "Further down, {riserTwo} moves above {riserTwoPassed}, {riserThree} above "
        "{riserThreePassed}, and {riserFour} above {riserFourPassed}.",
        "Every other pair keeps its order.",
    )

    # The next prompt contract: its reviewed immutable source, the three
    # facts the records name as unlisted, and the gates for a later run.
    # This evidence was retrieved from PR 173's head and verified against
    # the complete document's SHA256 before it was recorded in the note.
    links = {entry["label"]: entry["href"] for entry in note["data"]}
    assert links["Draft prompt contract (policybench#173)"] == (
        "https://github.com/PolicyEngine/policybench/pull/173"
    )
    # The draft adds policybench.prompt_contract_v2, which this tree lacks.
    assert not (ROOT / "policybench/prompt_contract_v2.py").exists()
    evidence = note["v2ContractEvidence"]
    assert evidence["pullRequest"] == 173
    assert evidence["commit"] == "41061fcaa1727a284e279fb763728dc3b36b8cbf"
    assert evidence["path"] == "docs/prompt_contract_v2.md"
    assert evidence["sha256"] == (
        "c532a028b562a7358480ffd872501a70f6d04842df640747983cc667565a8dc6"
    )
    assert evidence["version"] == "2.1.0"
    assert links["Draft v2 contract conventions (reviewed source)"] == (
        "https://github.com/PolicyEngine/policybench/blob/"
        f"{evidence['commit']}/{evidence['path']}"
        "#october-5-calculation-conventions"
    )
    assert evidence["excerpts"] == {
        "activation": (
            "`policybench.prompt_contract_v2` adds an **opt-in, unactivated "
            "household-fact\ncontract**"
        ),
        "salt": (
            "For each supplied tax unit, state the annual input\n"
            "`state_withheld_income_tax`, or follow the declared model's per-state "
            "AGI-based\nwithholding estimate and treat that estimate as paid "
            "during the year."
        ),
        "medicareEnrollment": (
            "Every person's text states `takes_up_medicare_if_eligible`: enrollment "
            "includes\nPart B and is assumed if eligible unless a supplied "
            "boolean overrides it."
        ),
        "medicarePremium": (
            "The annual enrollee payment `medicare_part_b_premium` is\n"
            "employee after-tax spending. When absent, it follows the declared "
            "model's\nstandard premium plus IRMAA, net of Medicare Savings "
            "Program support, and is\npaid only while enrolled."
        ),
        "employerChoice": (
            "For each person in MN Paid Leave, CO FAMLI, MA PFML, NY PFL/DBL, "
            "DE Paid Leave,\nME PFML, VT child-care contribution, or WA PFML, "
            "the prompt states whether\nthe employer withholds the employee share."
        ),
        "payrollScope": (
            "The v2 payroll definition covers all listed people's employee-side "
            "payroll\ntax, including dependent wages, mandatory state contributions, "
            "and optional\nemployee shares that the employer chooses to withhold "
            "under the stated\nconvention."
        ),
        "validation": (
            "Before activation, adapt the reference builder to the stated "
            "conventions and\nrun the complete sweep"
        ),
    }
    assert {by_key[k]["unlisted_input"].split(",")[0] for k in federal} == {SALT_INPUT}
    assert (
        "state in the payroll output's definition how these shares count, so a "
        "fresh run can score such households again"
    ) in payroll_readme
    pin(
        "PolicyBench's next prompt contract remains an unactivated draft "
        "(PolicyEngine/policybench#173).",
        "It states the state income tax paid for each tax unit or a named "
        "convention for estimating withholding; each person's Medicare Part B "
        "enrollment and annual net premium; and whether each person's employer "
        "withholds the employee share of state paid-leave or disability premiums.",
        "Its payroll output definition counts optional employee shares only "
        "when the employer withholds them.",
        "A later run can score these outputs after its reference builder and "
        "a fresh input sweep validate the stated conventions.",
    )
    assert (
        "whether its employer deducts the employee share of a state paid-leave or "
        "disability premium"
    ) in PAYROLL_INPUT.replace("the employer", "its employer")

    # The corrections. The model response window ends on the UTC date of the
    # last answer, which release 20260930 dated with its own snapshot date.
    import pandas as pd

    sys.path.insert(0, str(ROOT / "scripts"))
    from freeze_snapshot import model_response_window

    manifest = _load_json(_in(now_root, SNAPSHOT_DIR / "manifest.json"))
    previous_manifest = _load_json(_in(then_root, SNAPSHOT_DIR / "manifest.json"))
    completed = pd.read_csv(
        _in(now_root, PREDICTIONS_PATH),
        usecols=["request_completed_at"],
        dtype="float64",
        float_precision="round_trip",
    )["request_completed_at"].dropna()
    last_answer = datetime.fromtimestamp(completed.max(), tz=timezone.utc).date()
    start = manifest["model_response_date"].split(" to ")[0]
    assert manifest["model_response_date"] == (f"{start} to {last_answer.isoformat()}")
    assert manifest["model_response_date"] == model_response_window(
        _in(now_root, PREDICTIONS_PATH), spec["model_response_start"]
    )
    previous_end = previous_manifest["model_response_date"].split(" to ")[1]
    assert previous_end == previous_manifest["snapshot_date"] > last_answer.isoformat()
    assert RELEASE_20260930.endswith(previous_end.replace("-", ""))
    assert last_answer.year == date.fromisoformat(start).year == 2026
    # The paper page states the same window.
    assert _paper_snapshot(RELEASE_20261006)["responseWindow"] == (
        f"{facts['responseStart']} and {facts['responseEnd']}, {last_answer.year}"
    )
    # scenario_031's Medicaid text: the ledger's rewrites are the payload's
    # text now and were the previous release's, on a cell whose scores are
    # the same.
    medicaid = ("scenario_031", "head_medicaid_eligible")
    assert now["scenarios"][medicaid[0]]["state"] == "CA"
    assert _person(scenarios[medicaid[0]], "head")["age"] >= 65
    cell_now = now["scenarioPredictions"][medicaid[0]][medicaid[1]]
    cell_then = then["scenarioPredictions"][medicaid[0]][medicaid[1]]
    text_fields = {"annotation", "caseAnnotation", "referenceExplanation"}
    for model, entry in cell_now.items():
        assert {k: v for k, v in entry.items() if k not in text_fields} == {
            k: v for k, v in cell_then[model].items() if k not in text_fields
        }
    payload_field = {
        "case_annotation": "caseAnnotation",
        "explanation": "referenceExplanation",
        "annotation": "annotation",
    }
    rewrites = _load_json(MEDICAID_031_AUDIT / "rewrites.json")["rewrites"]
    assert len(rewrites) == 45
    for item in rewrites:
        assert (item["scenario_id"], item["variable"]) == medicaid
        field = payload_field[item["field"]]
        # A case-level text rides on every cell that carries the field: the
        # annotated rows for the case note, every row for the reference
        # explanation.
        carried = {m for m, entry in cell_now.items() if field in entry}
        assert carried == {m for m, entry in cell_then.items() if field in entry}
        models = [item["model"]] if "model" in item else sorted(carried)
        assert models
        for model in models:
            assert cell_now[model][field] == item["new"], (model, field)
            assert cell_then[model][field] == item["old"], (model, field)
    case_now = next(e for e in cell_now.values() if "caseAnnotation" in e)[
        "caseAnnotation"
    ]
    case_then = next(e for e in cell_then.values() if "caseAnnotation" in e)[
        "caseAnnotation"
    ]
    assert (
        "In place of SSI's $20 monthly general income exclusion, the engine applies "
        "California's $230 monthly disregard"
    ) in case_now
    assert (
        "Countable income is gross income minus health insurance premiums, "
        "including the Medicare Part B standard premium"
    ) in case_then
    # The engine's values: the disregard replaces SSI's exclusion and brings
    # countable income under the limit, which SSI's exclusion alone does not;
    # the premium does not enter it.
    summary = medicaid_values["summary"]
    assert summary["disregard_annual"] == 12 * facts["medicaidDisregard"]
    assert summary["countable_income"] < summary["income_limit"]
    assert summary["gross_less_ssi_general_exclusion_only"] > summary["income_limit"]
    readings = medicaid_values["readings"]
    countable = "medicaid_optional_senior_or_disabled_countable_income"
    assert readings["no_part_b"][countable] == readings["modeled"][countable]
    assert "It applies California's $230 monthly income disregard instead." in (
        _readme(MEDICAID_031_AUDIT)
    )
    pin(
        "Two corrections in this release move no score.",
        "PolicyBench now reports that it collected model responses from "
        "{responseStart} to {responseEnd}, 2026, ending on the UTC date of the "
        f"last answer; release {RELEASE_20260930} gave {{previousResponseEnd}}, "
        "the date of that release.",
        "The audit text for a California household head's Medicaid eligibility "
        "now explains the head's income test as the engine applies it: "
        "California's ${medicaidDisregard} monthly income disregard, which takes "
        "the place of SSI's ${ssiExclusion} general income exclusion, brings "
        "countable income under the limit.",
        "The earlier text said the engine subtracts a Medicare Part B premium from "
        "income, which it does not.",
    )

    # The models the prose names, and no sentence left unpinned.
    display = {m: MODEL_DISPLAY_NAMES[m] for m in after}
    assert _named_models(text, display) == {
        "gpt-6-sol",
        "claude-opus-5.5",
        "gpt-5.6-sol",
        "claude-sonnet-5.5",
        "gpt-6-luna",
    }
    unpinned = text
    for sentence in pinned:
        unpinned = unpinned.replace(sentence, "", 1)
    assert not unpinned.strip(), unpinned

    # The links: each household by description, each record and audit, the
    # release and the one before it.
    blob = "https://github.com/PolicyEngine/policybench/blob/main/"
    for href in links.values():
        if href.startswith("/notes/"):
            assert (NOTES_DIR / f"{href.removeprefix('/notes/')}.json").is_file()
        if href.startswith(blob):
            assert (ROOT / href.removeprefix(blob)).is_file(), href
    tag = "https://github.com/PolicyEngine/policybench/releases/tag/"
    assert links["Dashboard data release"] == tag + note["release"]
    assert links[f"Previous release {RELEASE_20260930}"] == tag + RELEASE_20260930
    for label, path in (
        ("Exclusion record", EXCLUSIONS_PATH),
        ("Developer adjudications", ADJUDICATIONS_PATH),
        ("Audit of the state income tax in the federal deduction", SALT_AUDIT),
        ("Audit of the Medicare Part B premium", PART_B_AUDIT),
        ("Audit of the state payroll contributions", PAYROLL_AUDIT),
        ("Correction of the Medicaid audit text", MEDICAID_031_AUDIT),
    ):
        target = path / "README.md" if path.is_dir() else path
        assert links[label] == blob + target.relative_to(ROOT).as_posix()
    household_links = {
        f"{names['scenario_022']} household (federal income tax)": "scenario_022",
        f"{names['scenario_081']} household": "scenario_081",
        f"{names['scenario_114']} household": "scenario_114",
        f"{names['scenario_032']} household": "scenario_032",
        f"{names['scenario_043']} household": "scenario_043",
        f"{names['scenario_082']} household": "scenario_082",
        "California household head (Medicaid eligibility)": medicaid[0],
    }
    assert sorted(set(household_links.values()) - {medicaid[0]}) == sorted(states)
    for label, scenario_id in household_links.items():
        assert links[label] == f"/?country=us&scenario={scenario_id}#scenarios"
    assert not any(re.search(r"scenario_\d", label) for label in links)
    assert len(links) == len(note["data"]) == 10 + len(household_links)


@cache
def _bbce_facts_at(release: str) -> dict:
    """The BBCE note's facts recomputed on ``release``'s snapshot."""
    return _bbce_note_facts(_note(BBCE_NOTE), _release_root(release))


def test_bbce_note_describes_the_later_release() -> None:
    """The October 5 BBCE note keeps release 20260930's facts and closes with
    the one that moves on release 20261006. Recomputed on release 20261006,
    every other fact of the note is the same, and the release changes no
    SNAP reference or answer."""
    note = _note(BBCE_NOTE)
    assert note["release"] == RELEASE_20260930
    assert note["paragraphs"][-1] == (
        f"{LATER_RELEASE_OPENING}{RELEASE_20261006}, stops scoring "
        "{laterExclusions:words} tax outputs and changes no SNAP reference or "
        "answer. On it, GPT-6 Luna is #{laterLunaRank} on PolicyBench, below "
        "Claude Sonnet 5.5, and every other figure in this note stays the same."
    )
    assert not any(RELEASE_20261006 in p for p in note["paragraphs"][:-1])
    links = {entry["label"]: entry["href"] for entry in note["data"]}
    assert links[f"Later release {RELEASE_20261006}"] == (
        "https://github.com/PolicyEngine/policybench/releases/tag/" + RELEASE_20261006
    )
    later_note = _note(EXCLUSIONS_NOTE)
    assert (
        links[f"Release note for {RELEASE_20261006} ({_month_day(later_note['date'])})"]
        == f"/notes/{EXCLUSIONS_NOTE}"
    )

    then = _bbce_facts_at(RELEASE_20260930)
    later = _bbce_facts_at(RELEASE_20261006)
    assert {key for key in then if later[key] != then[key]} == {"lunaRank"}
    assert _later_facts(note) == {
        "laterExclusions": len(_new_exclusions()),
        "laterLunaRank": later["lunaRank"],
    }
    assert later_note["facts"]["newExclusions"] == len(_new_exclusions())
    # The new tax exclusions are the only change, and none is a SNAP output.
    assert not [e for e in _new_exclusions() if e["variable"] == "snap"]
    now = _payload_at(_release_root(RELEASE_20261006))
    previous = _payload_at(_release_root(RELEASE_20260930))
    fields = ("prediction", "groundTruth", "scored", "exact", "explanation")
    for scenario_id, variables in now["scenarioPredictions"].items():
        for model, entry in variables["snap"].items():
            before = previous["scenarioPredictions"][scenario_id]["snap"][model]
            assert {k: entry.get(k) for k in fields} == {
                k: before.get(k) for k in fields
            }, (scenario_id, model)
    # GPT-6 Luna falls one place, below Claude Sonnet 5.5.
    board = [r for r in now["modelStats"] if r["condition"] == "no_tools"]
    exact = _no_tools_exact(now)
    assert later["lunaRank"] == then["lunaRank"] + 1
    assert _rank(exact["claude-sonnet-5.5"], board) == later["lunaRank"] - 1


# --- Release dashboard-data-20261009: Claude Haiku 5.5 and the engine move ----

(HAIKU_NOTE,) = sorted(
    path.stem for path in NOTES_DIR.glob("*-claude-haiku-5-5-joins-the-board.json")
)
HAIKU_SENSITIVITY = ROOT / "sensitivity/data/claude-haiku-5-5-thinking.json"


def _key_of(entry: dict) -> tuple[str, str]:
    return entry["scenario_id"], entry["variable"]


@cache
def _release_20261009_scoring() -> dict:
    """What moves the earlier models' rates between release 20261006 and this
    one, recomputed from the frozen predictions and weights: every model's
    exact rate on this release's scored references (``now``), the same with
    the restored outputs release 20261006 had excluded left unscored
    (``without``), those outputs (``newly_scored``) and how many models'
    answers the payload marks exact on each (``matched``)."""
    import pandas as pd

    from policybench.paper_results import PaperResults
    from policybench.scorer_vectors import canonical_filtered_scores
    from policybench.spec import output_group_id

    def excluded_at(root: Path) -> set[tuple[str, str]]:
        return {
            (e["scenario_id"], e["variable"])
            for e in _load_json(_in(root, EXCLUSIONS_PATH))["exclusions"]
        }

    payload = _dashboard()
    reference = pd.read_csv(REFERENCES_PATH)
    excluded = excluded_at(ROOT)
    restored = PaperResults().last_engine_upgrade.restored
    assert not restored & excluded
    newly_scored = sorted(restored & excluded_at(_release_root(RELEASE_20261006)))
    predictions = pd.DataFrame(
        [
            (model, scenario_id, variable, entry.get("prediction"))
            for scenario_id, outputs in payload["scenarioPredictions"].items()
            for variable, by_model in outputs.items()
            for model, entry in by_model.items()
        ],
        columns=["model", "scenario_id", "variable", "prediction"],
    )
    weights: dict[str, float] = {}
    for variable, weight in payload["globalWeights"]["household"].items():
        group = output_group_id(variable)
        weights[group] = weights.get(group, 0.0) + weight

    def board(unscored: set[tuple[str, str]]) -> dict[str, float]:
        keys = zip(reference["scenario_id"], reference["variable"], strict=True)
        scored = reference[[key not in unscored for key in keys]]
        scores, _ = canonical_filtered_scores(
            scored, predictions, weights, set(weights), "all", "exact"
        )
        return scores

    return {
        "now": board(excluded),
        "without": board(excluded | set(newly_scored)),
        "newly_scored": newly_scored,
        # The payload marks an answer's exact hit as 100.0, a miss as 0.0.
        "matched": {
            key: sum(
                entry["exact"] == 100.0
                for entry in payload["scenarioPredictions"][key[0]][key[1]].values()
            )
            for key in newly_scored
        },
    }


def _release_20261009_facts() -> dict:
    """The Claude Haiku 5.5 release note's facts, recomputed from the frozen
    release's payload, sidecar and exclusion record, from release 20261006's
    payload at its commit, and from the committed sensitivity summary."""
    from policybench.paper_results import PaperResults

    r = PaperResults()
    board = r.model_stats
    by_model = {row["model"]: row for row in board}
    ranks = {row["model"]: index + 1 for index, row in enumerate(board)}
    then = {
        row["model"]: row["exact"]
        for row in _payload_at(_release_root(RELEASE_20261006))["modelStats"]
        if row["condition"] == "no_tools"
    }
    fall = [exact - by_model[model]["exact"] for model, exact in then.items()]
    scoring = _release_20261009_scoring()
    rise = [scoring["without"][model] - exact for model, exact in then.items()]
    matched = median(scoring["matched"].values())
    haiku, haiku45 = by_model["claude-haiku-5.5"], by_model["claude-haiku-4.5"]
    sensitivity = _load_json(HAIKU_SENSITIVITY)["sensitivity"]
    last = r.last_engine_upgrade
    changes = last.partition["scored_changes"]
    assert len(changes) == 1 and changes[0]["scenario_id"] == "scenario_076"

    def one(value: float) -> float:
        return float(f"{value:.1f}")

    return {
        "releaseDate": r.manifest["snapshot_date"],
        "nModels": len(board),
        "haikuExact": one(haiku["exact"]),
        "haikuRank": ranks["claude-haiku-5.5"],
        "haiku45Exact": one(haiku45["exact"]),
        "haiku45Rank": ranks["claude-haiku-4.5"],
        # The gain the note prints is the difference of the rates it prints.
        "haikuGain": one(one(haiku["exact"]) - one(haiku45["exact"])),
        "solExact": one(by_model["gpt-6-sol"]["exact"]),
        "opusExact": one(by_model["claude-opus-5.5"]["exact"]),
        "sol56Exact": one(by_model["gpt-5.6-sol"]["exact"]),
        "haikuCost": round(haiku["costPerHousehold"], 4),
        "haiku45Cost": round(haiku45["costPerHousehold"], 4),
        "haikuAutoExact": one(sensitivity["exact"]),
        "haikuAutoRank": _rank(sensitivity["exact"], board),
        "previousEngine": r.previous_policyengine_us_version,
        "engineVersion": r.policyengine_us_version,
        "restored": r.engine_upgrade_restored_count,
        "restoredRuled": r.engine_upgrade_restored_count - len(scoring["newly_scored"]),
        "restoredFixes": r.engine_upgrade_restored_fix_phrase,
        "adversaryOutputs": r.ruled_decision_count("d1022"),
        "louisianaOutputs": r.ruled_decision_count("d994"),
        "indianaOutputs": r.engine_upgrade_new_exclusion_count,
        "idahoBefore": f"{changes[0]['previous']:,.2f}",
        "idahoAfter": f"{changes[0]['regenerated']:,.2f}",
        "scoredOutputs": int(r.scored_outputs_per_model_fmt.replace(",", "")),
        "totalOutputs": int(r.total_outputs_per_model_fmt.replace(",", "")),
        "excluded": r.excluded_output_count,
        "incumbents": len(then),
        "fallMin": round(min(fall), 2),
        "fallMax": round(max(fall), 2),
        "newlyScored": len(scoring["newly_scored"]),
        "newlyScoredMedianMatched": int(matched)
        if matched == int(matched)
        else matched,
        "newlyScoredUnmatched": sum(n == 0 for n in scoring["matched"].values()),
        "riseWithoutMin": round(min(rise), 2),
        "riseWithoutMax": round(max(rise), 2),
    }


def test_release_20261009_note() -> None:
    """The Claude Haiku 5.5 release note's facts are the frozen release's,
    recomputed from its payload, sidecar and exclusion record and from release
    20261006 at its commit; and the direction its last paragraph states (every
    earlier model's rate falls, and would have risen without the newly scored
    outputs) holds. test_release_20261009_note_claims checks the rest of what
    its sentences say, on the recomputed facts."""
    note = _note(HAIKU_NOTE)
    facts = note["facts"]
    assert note["release"] == _frozen_release()
    assert note["boardSnapshot"] == facts["releaseDate"] == note["date"]
    assert note["slug"].startswith(note["date"])
    assert facts["engineVersion"] in note["title"]
    assert facts == _release_20261009_facts()
    assert 0 < facts["fallMin"] <= facts["fallMax"]
    assert 0 < facts["riseWithoutMin"] <= facts["riseWithoutMax"]


def test_release_20261009_note_claims() -> None:
    """What the Claude Haiku 5.5 release note's sentences claim holds on the
    frozen release, checked on the facts recomputed from it (so these checks
    run even while the note's own facts await the release)."""
    from policybench.analysis import metric_type_for_output, row_hit_scores
    from policybench.model_cards import card_for
    from policybench.paper_results import PaperResults

    note = _note(HAIKU_NOTE)
    facts = _release_20261009_facts()
    r = PaperResults()
    board = r.model_stats
    # Claude Haiku 5.5 is new, and the cheapest row with a recorded cost.
    assert facts["nModels"] == facts["incumbents"] + 1
    paid = [row for row in board if row["costUsd"] > 0]
    assert min(paid, key=lambda row: row["costPerHousehold"])["model"] == (
        "claude-haiku-5.5"
    )
    # GPT-6 Sol leads, ahead of Claude Opus 5.5 and GPT-5.6 Sol, in that order.
    assert [row["model"] for row in board[:3]] == [
        "gpt-6-sol",
        "claude-opus-5.5",
        "gpt-5.6-sol",
    ]
    # The recomputed board is the payload's, and the payload's exact marks are
    # the scorer's.
    scoring = _release_20261009_scoring()
    assert set(scoring["now"]) == {row["model"] for row in board}
    for row in board:
        assert scoring["now"][row["model"]] == pytest.approx(row["exact"], abs=1e-9)
    restored = r.last_engine_upgrade.restored
    assert 0 < facts["newlyScored"] <= facts["restored"] == len(restored)
    assert set(scoring["newly_scored"]) <= restored
    # The restored outputs release 20261006 still scored are exactly the
    # October 6 engine defects, which this release would otherwise exclude.
    defect_keys = {
        (e["scenario_id"], e["variable"])
        for e in r.ruled_records
        if e["reason_code"] == "reference_engine_defect"
    }
    assert restored - set(scoring["newly_scored"]) == defect_keys
    # "The cause is" the newly scored outputs: nothing else an incumbent is
    # scored on moved. Every incumbent's answers and the household weights are
    # release 20261006's.
    then_payload = _payload_at(_release_root(RELEASE_20261006))
    assert r.dashboard["globalWeights"] == then_payload["globalWeights"]
    for scenario_id, outputs in then_payload["scenarioPredictions"].items():
        for variable, by_model in outputs.items():
            now = r.dashboard["scenarioPredictions"][scenario_id][variable]
            for model, entry in by_model.items():
                assert now[model]["prediction"] == entry["prediction"], (
                    scenario_id,
                    variable,
                    model,
                )
    assert facts["restoredRuled"] + facts["newlyScored"] == facts["restored"]
    # "Each lands within $1 of the corrected value PolicyBench's audits
    # computed": every restored output's target holds (record or fix modules).
    targets = r.engine_upgrade_restored_targets
    assert len(targets["record"]) + len(targets["fix_modules"]) == facts["restored"]
    # "Few models get right": the median output, by at most a tenth of them.
    assert facts["newlyScoredMedianMatched"] <= facts["nModels"] / 10
    for (scenario_id, variable), matched in scoring["matched"].items():
        # "Within $1" is the scorer's exact rule for an amount output.
        assert metric_type_for_output(variable) == "amount"
        entries = r.dashboard["scenarioPredictions"][scenario_id][variable]
        assert len(entries) == facts["nModels"]
        assert all(entry["scored"] for entry in entries.values())
        assert {entry["exact"] for entry in entries.values()} <= {0.0, 100.0}
        assert matched == sum(
            row_hit_scores(variable, entry["groundTruth"], entry["prediction"])["exact"]
            for entry in entries.values()
        )
    # The four defects the adversary found are among the restored outputs,
    # and the other four of its eight, with Louisiana's two, stay excluded.
    ruled = r.ruled_records
    defects = [e for e in ruled if e["reason_code"] == "reference_engine_defect"]
    assert len(defects) == 4 and all(
        (e["scenario_id"], e["variable"]) in restored for e in defects
    )
    states = {
        e["scenario_id"]: r.dashboard["scenarios"][e["scenario_id"]]["state"]
        for e in ruled
    }
    assert sorted(states[e["scenario_id"]] for e in defects) == ["AZ", "CO", "NY", "OH"]
    kept = [e for e in ruled if e["reason_code"] != "reference_engine_defect"]
    assert Counter((states[e["scenario_id"]], e["decision"]) for e in kept) == Counter(
        {("PA", "d1022"): 2, ("MO", "d1022"): 2, ("LA", "d994"): 2}
    )
    assert facts["adversaryOutputs"] == 8 and facts["louisianaOutputs"] == 2
    # The four kept d1022 outputs are the federal and state income tax of one
    # Pennsylvania and one Missouri household, whose dependent has $45,000 of
    # wages and must file their own return.
    taxes = {
        "federal_income_tax_before_refundable_credits",
        "state_income_tax_before_refundable_credits",
    }
    scope = [e for e in kept if e["decision"] == "d1022"]
    by_household: dict[str, set[str]] = {}
    for e in scope:
        by_household.setdefault(e["scenario_id"], set()).add(e["variable"])
    assert len(by_household) == 2 and all(v == taxes for v in by_household.values())
    for e in scope:
        assert "$45,000 of wages must file their own" in e["alternative_reading"]
        assert "must file their own" in e["unlisted_input"]
    # Louisiana's two outputs are two households' state income tax; the record
    # names the price-index computation and the September 28 publication.
    louisiana = [e for e in kept if e["decision"] == "d994"]
    assert len({e["scenario_id"] for e in louisiana}) == 2
    for e in louisiana:
        assert e["variable"] == "state_income_tax_before_refundable_credits"
        assert "CPI-U" in e["alternative_reading"] and "CPI-U" in e["law"]
        assert "dated 2026-09-28" in e["published"]
    # The Indiana outputs are local income tax; the Idaho change is its
    # $10 permanent building fund tax.
    new = r.last_engine_upgrade.partition["new_exclusions"]
    assert {c["variable"] for c in new} == {"local_income_tax"}
    assert {r.dashboard["scenarios"][c["scenario_id"]]["state"] for c in new} == {"IN"}
    assert len({c["scenario_id"] for c in new}) == facts["indianaOutputs"]
    # "The prompt names no county": the record says so, and no prompt does.
    for c in new:
        (record,) = [e for e in r.reference_exclusions if _key_of(e) == _key_of(c)]
        assert record["unlisted_input"].startswith("county of residence")
        prompt = r.dashboard["scenarios"][c["scenario_id"]]["prompt"]
        assert "county" not in json.dumps(prompt).lower()
    (change,) = r.last_engine_upgrade.partition["scored_changes"]
    assert r.dashboard["scenarios"][change["scenario_id"]]["state"] == "ID"
    assert change["regenerated"] - change["previous"] == pytest.approx(10.0)
    assert "permanent building fund" in change["basis"]
    # The serving claims of the cost paragraph are the model card's.
    card = card_for("claude-haiku-5-5")
    assert card.answer_contract == "tool"
    assert "forced-tool probe returned no thinking block" in card.notes
    # "where a request without the forced tool did": the unforced probe.
    assert "A request with no thinking parameter returns a thinking block" in (
        card.notes
    )
    assert "as Claude Opus 5's row does" in card.notes
    # "Under the same publication conventions": the move keeps every
    # convention module of the move before it.
    upgrades = [x for x in r.reference_revisions if x.get("kind") == "engine_upgrade"]
    conventions = [
        {m["module"] for m in u["fix_modules"] if m["module"].startswith("latest_c")}
        for u in upgrades[-2:]
    ]
    assert conventions[0] == conventions[1] and conventions[0]
    assert facts["scoredOutputs"] == facts["totalOutputs"] - facts["excluded"]
    # Links resolve to committed paths.
    for entry in note["data"]:
        href = entry["href"]
        prefix = "https://github.com/PolicyEngine/policybench/blob/main/"
        if href.startswith(prefix):
            assert (ROOT / href.removeprefix(prefix)).exists(), href
    text = " ".join(note["paragraphs"])
    assert "{restoredFixes}" in text
    assert "newest" not in text
