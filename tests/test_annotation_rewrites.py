"""Committed rewrites of frozen audit annotations stay in force and stay wording-only.

reference_audit/2026-10-05-medicaid-031-annotations/rewrites.json corrects the text
that explained scenario_031's head Medicaid reference with a Medicare Part B premium
the engine never subtracts. A later release that rebuilds the annotation files from
an older base must carry these rewrites (or supersede the ledger), or these tests
fail.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "reference_audit" / "2026-10-05-medicaid-031-annotations"
MANIFEST = ROOT / "paper" / "snapshot" / "20260501" / "manifest.json"
KEYS = {
    "us_audit_row_annotations.csv": ("scenario_id", "variable", "model"),
    "us_case_notes.csv": ("scenario_id", "variable"),
    "us_case_reference_explanations.csv": ("scenario_id", "variable"),
}
FIELDS = {
    "us_audit_row_annotations.csv": "annotation",
    "us_case_notes.csv": "case_annotation",
    "us_case_reference_explanations.csv": "explanation",
}


def _rewrites() -> list[dict]:
    return json.loads((AUDIT / "rewrites.json").read_text())["rewrites"]


def _annotation_dir() -> Path:
    manifest = json.loads(MANIFEST.read_text())
    return ROOT / manifest["audit_annotation_artifacts"]["path"]


def _rows(name: str) -> list[dict]:
    with (_annotation_dir() / name).open(newline="") as source:
        return list(csv.DictReader(source))


def test_every_rewrite_is_in_force():
    for name, key_columns in KEYS.items():
        items = [item for item in _rewrites() if item["file"] == name]
        rows = _rows(name)
        index = {}
        for row in rows:
            index.setdefault(tuple(row[c] for c in key_columns), []).append(row)
        for item in items:
            key = tuple(item[c] for c in key_columns)
            assert len(index.get(key, [])) == 1, (name, key)
            assert index[key][0][FIELDS[name]] == item["new"], (name, key)


def test_no_rewritten_text_survives_anywhere():
    old_texts = {item["old"] for item in _rewrites()}
    for name, field in FIELDS.items():
        for row in _rows(name):
            assert row[field] not in old_texts, (name, row["scenario_id"])


def test_rewrites_are_wording_only_and_well_formed():
    rewrites = _rewrites()
    assert rewrites
    keys = set()
    for item in rewrites:
        assert item["file"] in KEYS
        assert item["field"] == FIELDS[item["file"]]
        assert item["old"] != item["new"]
        assert item["reason"].strip()
        key = (item["file"], *(item[c] for c in KEYS[item["file"]]))
        assert key not in keys, key
        keys.add(key)
        # A rewrite carries text only: no class, source or subtype field.
        assert set(item) <= {
            "file",
            "field",
            "scenario_id",
            "variable",
            "model",
            "old",
            "new",
            "reason",
        }


def test_rewritten_rows_keep_their_classes():
    """The rows stay model errors; the rewrites change no failure class."""
    rewritten = {
        (item["scenario_id"], item["variable"], item["model"])
        for item in _rewrites()
        if item["file"] == "us_audit_row_annotations.csv"
    }
    rows = [
        row
        for row in _rows("us_audit_row_annotations.csv")
        if (row["scenario_id"], row["variable"], row["model"]) in rewritten
    ]
    assert len(rows) == len(rewritten)
    assert {row["failure_source"] for row in rows} == {"llm_error"}
    assert {row["reference_suspect"] for row in rows} == {"False"}


def test_engine_record_backs_the_figures_the_text_states():
    """The recomputed engine values are the ones the case note and explanation give."""
    record = json.loads((AUDIT / "verification" / "engine_values.json").read_text())
    summary = record["summary"]
    assert record["published_reference"] == 1.0
    assert summary["countable_income"] <= summary["income_limit"]
    for reading in ("no_part_b", "not_enrolled"):
        assert (
            record["readings"][reading][
                "medicaid_optional_senior_or_disabled_countable_income"
            ]
            == record["readings"]["modeled"][
                "medicaid_optional_senior_or_disabled_countable_income"
            ]
        )
    figures = [
        f"${summary['gross_unearned_income']:,.2f}",
        f"${summary['countable_income']:,.2f}",
        f"${summary['income_limit']:,.2f}",
    ]
    for name in ("us_case_notes.csv", "us_case_reference_explanations.csv"):
        (row,) = [
            row
            for row in _rows(name)
            if (row["scenario_id"], row["variable"])
            == ("scenario_031", "head_medicaid_eligible")
        ]
        for figure in figures:
            assert figure in row[FIELDS[name]], (name, figure)
