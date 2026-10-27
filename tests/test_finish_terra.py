"""Terra's one-model release keeps Argon's gates and installs the audited build.

Runs, audits and payloads below are synthetic. The builder compatibility test
reads the committed October 22 build and reconstructs its narratives offline
inside pytest's temporary directory. Nothing writes published data or calls an
engine, provider or network service.
"""

from __future__ import annotations

import copy
import csv
import functools
import hashlib
import inspect
import json
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import finish_terra as driver  # noqa: E402
import release_20261006  # noqa: E402

from policybench.audit import AUDIT_OUTPUT_SCHEMA  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
NEW, SLUG = "gpt-6.1-terra", "terra"
SNAPSHOT_PATH = Path("paper/snapshot/20260501/runs") / driver.RUN_NAME
CSV_NAME = "reference_outputs.csv"
META_NAME = "reference_outputs.csv.meta.json"
EXCLUSIONS_NAME = "reference_exclusions.json"
MOVED = {
    ("scenario_028", "free_school_meals_eligible"): 1.0,
    ("scenario_031", "snap"): 288.0,
    ("scenario_117", "free_school_meals_eligible"): 1.0,
    ("scenario_123", "free_school_meals_eligible"): 1.0,
}


def sha(value: bytes | Path) -> str:
    return hashlib.sha256(
        value.read_bytes() if isinstance(value, Path) else value
    ).hexdigest()


@functools.cache
def base_blob(path: Path) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(REPO), "show", f"{driver.BASE_COMMIT}:{path.as_posix()}"],
        check=True,
        capture_output=True,
    )
    return result.stdout


def base_references(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    for name in driver.REFERENCE_FILES:
        (directory / name).write_bytes(base_blob(SNAPSHOT_PATH / name))
    return directory


def real_spec() -> dict:
    return json.loads((REPO / driver.SPEC_PATH).read_text())


def test_terra_alone_joins_the_50_model_base():
    assert driver.MODELS == {SLUG: NEW}
    assert (driver.BASE_MODELS, driver.BOARD_MODELS) == (50, 51)
    assert (driver.BASE_OUTPUTS, driver.BASE_EXCLUSIONS, driver.BASE_SCORED) == (
        1984,
        49,
        1935,
    )
    assert driver.BASE_TAG == "dashboard-data-20261014"
    assert driver.BASE_COMMIT == "bf845cbe4e92de495150c8660c35ea357d996a8c"
    assert driver.SEED_RELEASE_COMMIT == driver.BASE_COMMIT
    assert driver.JUDGE_TEMPLATE_VERSION == 2
    assert driver.REWORDED_SINCE_SEED == frozenset()


def test_the_spec_starts_without_proposals_or_adjudications():
    spec = real_spec()
    assert spec["release_tag"] == driver.RELEASE_TAG
    assert spec["base_tag"] == driver.BASE_TAG
    assert spec["base_sha256"] == driver.BASE_SHA256
    assert spec["proposals"] == []
    assert spec["adjudications"] == []
    assert spec["triage_adjudications"] == []


def test_the_base_pointer_and_reference_pins_are_the_release_bytes(tmp_path):
    pointer = json.loads(base_blob(Path("app/src/data.artifact.json")))
    assert pointer["tag"] == driver.BASE_TAG
    assert pointer["sha256"] == driver.BASE_SHA256
    directory = base_references(tmp_path / "base")
    driver.verify_reference_pins(directory, "base")
    assert set(driver.BASE_REFERENCE_SHA256) == set(driver.REFERENCE_FILES)
    assert {
        name: sha(directory / name) for name in driver.REFERENCE_FILES
    } == driver.BASE_REFERENCE_SHA256


@pytest.fixture
def runs(tmp_path):
    root = tmp_path / "runs"
    run = root / SLUG / "run"
    run.mkdir(parents=True)
    driver.write_json(
        run / "run_state.json",
        {"model": NEW, "completed": 100, "total": 100, "stopped_reason": None},
    )
    (run / "predictions.csv").write_text("model,scenario_id,variable\n")
    return root


def test_discovery_finds_only_terra(runs):
    extra = runs / "scratch/run"
    extra.mkdir(parents=True)
    driver.write_json(extra / "run_state.json", {"model": "other"})
    found = driver.discover_new_models(runs)
    assert [(run.slug, run.model) for run in found] == [(SLUG, NEW)]


@pytest.mark.parametrize(
    "changes",
    [
        {"completed": 99},
        {"total": 0, "completed": 0},
        {"total": True, "completed": True},
        {"total": 100.0},
        {"stopped_reason": "budget"},
        {"stopped_reason": ""},
        {"model": "gpt-6.1-sol"},
    ],
)
def test_discovery_refuses_an_unfinished_or_different_run(runs, changes):
    path = runs / SLUG / "run/run_state.json"
    state = json.loads(path.read_text())
    driver.write_json(path, {**state, **changes})
    with pytest.raises(SystemExit, match="refusing incomplete additions"):
        driver.discover_new_models(runs)


@pytest.mark.parametrize("name", ["predictions.csv", "run_state.json"])
def test_discovery_requires_both_run_files(runs, name):
    (runs / SLUG / "run" / name).unlink()
    with pytest.raises(SystemExit, match=SLUG):
        driver.discover_new_models(runs)


def test_pin_inputs_hashes_both_completed_run_files(runs, tmp_path, monkeypatch):
    pins = tmp_path / "pins.json"
    monkeypatch.setattr(driver, "INPUT_PINS", pins)
    driver.main(["--step", "pin-inputs", "--runs-root", str(runs)])
    record = json.loads(pins.read_text())
    assert record["inputs"] == {
        SLUG: {
            "run": f"runs/{SLUG}/run",
            "sha256": {
                name: sha(runs / SLUG / "run" / name) for name in driver.PINNED_INPUTS
            },
        }
    }


def scratch_commit(root: Path, message: str) -> None:
    git = [
        "git",
        "-C",
        str(root),
        "-c",
        "core.hooksPath=/dev/null",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
    ]
    subprocess.run([*git, "add", "."], check=True)
    subprocess.run([*git, "commit", "--allow-empty", "-qm", message], check=True)


@pytest.fixture
def pinned_repo(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    pins = root / driver.INPUT_PINS_PATH
    pins.parent.mkdir(parents=True)
    record = {
        "inputs": {
            SLUG: {
                "sha256": {
                    "predictions.csv": "a" * 64,
                    "run_state.json": "b" * 64,
                }
            }
        }
    }
    driver.write_json(pins, record)
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
    scratch_commit(root, "input pins")
    monkeypatch.setattr(driver, "ROOT", root)
    monkeypatch.setattr(driver, "INPUT_PINS", pins)
    return pins, record


def test_input_pins_bind_the_committed_bytes(pinned_repo):
    pins, record = pinned_repo
    assert driver.committed_input_pins() == {SLUG: record["inputs"][SLUG]["sha256"]}
    record["inputs"][SLUG]["sha256"]["predictions.csv"] = "c" * 64
    driver.write_json(pins, record)
    with pytest.raises(SystemExit, match="differs from its HEAD commit"):
        driver.committed_input_pins()


@pytest.mark.parametrize(
    "inputs",
    [
        {},
        {SLUG: {"sha256": {"predictions.csv": "a" * 64}}},
        {
            SLUG: {"sha256": {"predictions.csv": "a", "run_state.json": "b"}},
            "other": {},
        },
    ],
)
def test_incomplete_input_pins_are_refused(pinned_repo, inputs):
    pins, _ = pinned_repo
    driver.write_json(pins, {"inputs": inputs})
    scratch_commit(driver.ROOT, "changed pins")
    with pytest.raises(SystemExit, match="does not pin"):
        driver.committed_input_pins()


@pytest.fixture
def predictions():
    return pd.DataFrame(
        {
            "model": [NEW, NEW],
            "scenario_id": ["s1", "s1"],
            "variable": ["snap", "ssi"],
            "prediction": [0, 1],
        }
    )


def test_equal_row_counts_do_not_hide_substituted_keys(predictions):
    changed = predictions.copy()
    changed.loc[1, "variable"] = "other"
    with pytest.raises(SystemExit, match="keys differ"):
        driver.validate_keys(changed, predictions, NEW)


def test_duplicate_prediction_keys_are_refused(predictions):
    with pytest.raises(SystemExit, match="duplicate prediction keys"):
        driver.validate_keys(
            pd.concat([predictions, predictions.iloc[:1]]), predictions, NEW
        )


def test_predictions_cannot_name_another_model(predictions):
    with pytest.raises(SystemExit, match="unexpected model"):
        driver.validate_keys(predictions, predictions, "other")


def provenance_frame(**changes):
    return pd.DataFrame(
        [
            {
                "model": NEW,
                "scenario_id": "s1",
                "variable": "snap",
                "live_calls": 2,
                "cache_hit_calls": 1,
                "live_elapsed_seconds": 2.0,
                "elapsed_seconds": 3.0,
                **changes,
            }
        ]
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"live_calls": -1},
        {"cache_hit_calls": -1},
        {"live_calls": 0.5},
        {"cache_hit_calls": None},
        {"live_elapsed_seconds": float("nan")},
        {"live_elapsed_seconds": float("inf")},
        {"live_elapsed_seconds": -1},
        {"live_elapsed_seconds": 4},
        {"elapsed_seconds": float("nan")},
        {"elapsed_seconds": -1},
        {"live_calls": 0, "cache_hit_calls": 0},
        {"live_calls": 0, "cache_hit_calls": 1, "live_elapsed_seconds": 1},
    ],
)
def test_rows_need_valid_live_and_cache_call_disclosures(changes):
    with pytest.raises(SystemExit):
        driver.verify_call_provenance(provenance_frame(**changes), NEW)


@settings(max_examples=40, deadline=None)
@given(
    live=st.integers(0, 20),
    cached=st.integers(1, 20),
    elapsed=st.floats(0, 1000, allow_nan=False, allow_infinity=False),
)
def test_valid_call_disclosures_preserve_all_source_columns(live, cached, elapsed):
    frame = provenance_frame(
        live_calls=live,
        cache_hit_calls=cached,
        live_elapsed_seconds=elapsed if live else 0,
        elapsed_seconds=elapsed,
    )
    original = frame.copy(deep=True)
    driver.verify_call_provenance(frame, NEW)
    pd.testing.assert_frame_equal(frame, original)


@pytest.mark.parametrize(
    "column", ["live_calls", "cache_hit_calls", "live_elapsed_seconds"]
)
def test_modern_run_disclosures_cannot_be_omitted(column):
    with pytest.raises(SystemExit):
        driver.verify_call_provenance(provenance_frame().drop(columns=[column]), NEW)


@pytest.mark.parametrize(
    "column",
    [
        "live_calls",
        "cache_hit_calls",
        "live_elapsed_seconds",
        "elapsed_seconds",
        "cost_usd",
        "provider_system_fingerprint",
    ],
)
def test_folded_rows_preserve_every_original_disclosure(tmp_path, column):
    stage = tmp_path / "stage"
    inputs = stage / "inputs" / SLUG
    inputs.mkdir(parents=True)
    us = stage / "publish" / driver.RUN_NAME / "us"
    us.mkdir(parents=True)
    frame = provenance_frame(cost_usd="", provider_system_fingerprint="fp_synthetic")
    frame.to_csv(inputs / "predictions.csv", index=False)
    frame.to_csv(us / "predictions.csv", index=False)
    assert driver.new_model_row_differences(stage) == []
    frame[column] = "changed"
    frame.to_csv(us / "predictions.csv", index=False)
    assert any(
        column in difference for difference in driver.new_model_row_differences(stage)
    )


RUN_COLUMNS = (
    "model",
    "scenario_id",
    "variable",
    "prediction",
    "explanation",
    "raw_response",
    "error",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "reasoning_tokens",
    "cached_prompt_tokens",
    "cache_write_prompt_tokens",
    "provider_reported_cost_usd",
    "reconstructed_cost_usd",
    "total_cost_usd",
    "cost_is_estimated",
    "estimated_cost_usd",
    "elapsed_seconds",
    "live_calls",
    "cache_hit_calls",
    "live_elapsed_seconds",
    "request_started_at",
    "request_completed_at",
    "provider_resolved_model",
    "provider_system_fingerprint",
    "request_id",
    "condition",
    "temperature",
)


def write_csv(path: Path, header, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=header, lineterminator="\n", quoting=csv.QUOTE_ALL
        )
        writer.writeheader()
        writer.writerows(rows)


def read_csv_text(path: Path):
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        return reader.fieldnames, list(reader)


def restoration_fixture(root: Path, *, cells=None):
    """A pandas fold with promoted call counts and an untouched incumbent."""
    root.mkdir(parents=True, exist_ok=True)
    source = root / "source.csv"
    rows = []
    for index, variable in enumerate(("snap", "ssi")):
        row = dict.fromkeys(RUN_COLUMNS, "")
        row.update(
            {
                "model": NEW,
                "scenario_id": "s1",
                "variable": variable,
                "prediction": "0.0",
                "explanation": 'Synthetic, "quoted" answer.\nNext line.',
                "live_calls": str(index + 1),
                "cache_hit_calls": "0",
                "live_elapsed_seconds": "1.25",
                "elapsed_seconds": "1.50",
                "provider_resolved_model": NEW,
                **(cells or {}),
            }
        )
        rows.append(row)
    write_csv(source, RUN_COLUMNS, rows)
    header = [*RUN_COLUMNS, "legacy_only"]
    incumbent = {name: "" for name in header}
    incumbent.update(
        model="incumbent",
        scenario_id="s1",
        variable="snap",
        prediction="2.00",
        explanation='Incumbent, "original".',
        legacy_only="carried",
    )
    folded_rows = [incumbent]
    for row in reversed(rows):
        folded = {**row, "legacy_only": ""}
        for column in ("live_calls", "cache_hit_calls"):
            folded[column] = f"{row[column]}.0"
        folded_rows.append(folded)
    path = root / "folded.csv"
    write_csv(path, header, folded_rows)
    run = driver.NewRun(SLUG, NEW, root, source, {})
    return SimpleNamespace(
        path=path,
        source=source,
        rows=rows,
        run=run,
        header=header,
        folded_rows=folded_rows,
        incumbent=incumbent,
    )


def test_the_post_fold_restore_keeps_all_29_source_columns_as_text(tmp_path):
    s = restoration_fixture(tmp_path)
    assert len(RUN_COLUMNS) == 29
    driver.restore_run_row_text(s.path, [s.run])
    header, rows = read_csv_text(s.path)
    assert header == s.header
    assert rows[0] == s.incumbent
    keyed = {(row["scenario_id"], row["variable"]): row for row in rows[1:]}
    for original in s.rows:
        row = keyed[original["scenario_id"], original["variable"]]
        assert {name: row[name] for name in RUN_COLUMNS} == original
        assert row["legacy_only"] == ""
        assert row["live_calls"] in {"1", "2"}
        assert row["cache_hit_calls"] == "0"


@settings(max_examples=12, deadline=None)
@given(
    explanation=st.text(alphabet='abcXYZ012 ,"\n\réβ', max_size=40),
    cost=st.sampled_from(["", "0", "0.00", "0.250000", "1e-06"]),
    tokens=st.integers(0, 10**9).map(str),
)
def test_any_source_cell_text_survives_the_restore(
    tmp_path_factory, explanation, cost, tokens
):
    root = tmp_path_factory.mktemp("restore-text")
    s = restoration_fixture(
        root,
        cells={
            "explanation": explanation,
            "estimated_cost_usd": cost,
            "total_tokens": tokens,
        },
    )
    driver.restore_run_row_text(s.path, [s.run])
    _, rows = read_csv_text(s.path)
    assert rows[0] == s.incumbent
    source = {row["variable"]: row for row in s.rows}
    assert {
        row["variable"]: {key: row[key] for key in RUN_COLUMNS} for row in rows[1:]
    } == source


@pytest.mark.parametrize(
    "defect",
    [
        "missing_output",
        "duplicate_output",
        "replaced_key",
        "lost_column",
        "duplicate_source",
    ],
)
def test_the_restore_refuses_key_or_column_loss_without_writing(tmp_path, defect):
    s = restoration_fixture(tmp_path)
    rows = copy.deepcopy(s.folded_rows)
    header = s.header
    if defect == "missing_output":
        rows.pop()
    elif defect == "duplicate_output":
        rows.append(rows[-1])
    elif defect == "replaced_key":
        rows[-1]["variable"] = "different"
    elif defect == "lost_column":
        header = [name for name in header if name != "live_calls"]
        rows = [{name: row[name] for name in header} for row in rows]
    else:
        write_csv(s.source, RUN_COLUMNS, [*s.rows, s.rows[-1]])
    write_csv(s.path, header, rows)
    before = s.path.read_bytes()
    with pytest.raises(SystemExit, match="keys|columns|outputs"):
        driver.restore_run_row_text(s.path, [s.run])
    assert s.path.read_bytes() == before
    assert not s.path.with_name(s.path.name + ".restoring").exists()


@pytest.mark.parametrize("missing", [None, float("nan")])
def test_usage_validation_accepts_missing_recorded_usage(missing):
    frame = pd.DataFrame(
        {"estimated_cost_usd": [missing, 0.0, 0.25], "total_tokens": [missing, 0, 123]}
    )
    before = frame.copy(deep=True)
    driver.verify_usage(frame, NEW)
    pd.testing.assert_frame_equal(frame, before)


@pytest.mark.parametrize("column", ["estimated_cost_usd", "total_tokens"])
@pytest.mark.parametrize("value", [-1, float("inf"), float("-inf"), "unreported"])
def test_usage_validation_refuses_invalid_recorded_values(column, value):
    frame = pd.DataFrame({"estimated_cost_usd": [0.25], "total_tokens": [100]})
    frame[column] = value
    with pytest.raises(SystemExit, match=column):
        driver.verify_usage(frame, NEW)


@pytest.mark.parametrize("column", ["estimated_cost_usd", "total_tokens"])
def test_usage_validation_requires_the_recorded_columns(column):
    frame = pd.DataFrame({"estimated_cost_usd": [None], "total_tokens": [None]})
    with pytest.raises(SystemExit, match=column):
        driver.verify_usage(frame.drop(columns=[column]), NEW)


@pytest.mark.parametrize("prompt,completion", [(None, None), (None, 100), (100, None)])
def test_missing_terra_usage_cannot_be_priced_as_zero(prompt, completion):
    from policybench.analysis import model_cost_latency

    frame = pd.DataFrame(
        [
            {
                "model": NEW,
                "scenario_id": "s1",
                "variable": "snap",
                "prediction": 0.0,
                "estimated_cost_usd": None,
                "total_tokens": None,
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "elapsed_seconds": 2.0,
            }
        ]
    )
    driver.verify_usage(frame, NEW)
    usage = model_cost_latency(frame, {NEW: {"input": 1.0, "output": 2.0}})
    assert usage == {NEW: {"latencySeconds": 2.0}}


def test_a_recorded_terra_zero_cost_stays_zero():
    from policybench.analysis import model_cost_latency

    frame = pd.DataFrame(
        [
            {
                "model": NEW,
                "scenario_id": "s1",
                "variable": "snap",
                "prediction": 0.0,
                "estimated_cost_usd": 0.0,
                "total_cost_usd": 0.0,
                "total_tokens": 0,
                "elapsed_seconds": 2.0,
            }
        ]
    )
    driver.verify_usage(frame, NEW)
    usage = model_cost_latency(frame, {NEW: {"input": 1.0, "output": 2.0}})
    assert usage[NEW]["costUsd"] == 0.0
    assert usage[NEW]["costPerHousehold"] == 0.0


def _verdict(models, source="llm_error"):
    return {
        "reference_suspect": False,
        "reference_bug_hypothesis": "",
        "case_failure_source": source,
        "case_failure_subtype": "thresholds_rates",
        "rationale": "The models applied an outdated threshold.",
        "models": [
            {
                "model": m,
                "failure_source": source,
                "failure_subtype": "thresholds_rates",
                "diagnosis": "The model used the prior year's threshold.",
            }
            for m in models
        ],
    }


def write_verdict(case, verdict, **meta):
    path = case / "verdict.json"
    driver.write_json(path, verdict)
    driver.write_json(
        case / "verdict.meta.json",
        {
            k: v
            for k, v in {
                "verdict_sha256": sha(path),
                "prompt_sha256": (
                    sha(case / "prompt.md") if (case / "prompt.md").is_file() else None
                ),
                "judge_runner": "scripts/run_audit_claude.sh",
                "judge_model_requested": driver.JUDGE_MODEL,
                "judge_model_reported": [driver.JUDGE_MODEL],
                "judged_at_utc": "2026-10-26T12:00:00+00:00",
                "judge_template_version": driver.JUDGE_TEMPLATE_VERSION,
                **meta,
            }.items()
            if v is not None
        },
    )


@pytest.fixture
def audit(tmp_path):
    from policybench.judge_template import template_header

    root = tmp_path / "audit"
    case = root / "cases/us__s1__snap"
    case.mkdir(parents=True)
    (case / "prompt.md").write_text(template_header(2) + "\nSynthetic question.\n")
    driver.write_json(root / "schema.json", AUDIT_OUTPUT_SCHEMA)
    (root / "cases.jsonl").write_text(
        json.dumps(
            {
                "case_id": case.name,
                "wrong_models": [NEW],
                "parse_failure_only": False,
            }
        )
        + "\n"
    )
    verdict = _verdict([NEW])
    write_verdict(case, verdict)
    return root, case, verdict


def test_a_bound_v2_opus_verdict_passes(audit):
    assert driver.validate_verdicts(audit[0]) == []


@pytest.mark.parametrize("defect", ["missing", "extra", "duplicate", "schema", "json"])
def test_invalid_verdicts_are_pending_and_removed_with_their_sidecars(audit, defect):
    root, case, original = audit
    verdict = copy.deepcopy(original)
    if defect == "missing":
        verdict["models"] = []
    elif defect == "extra":
        verdict["models"].append({**verdict["models"][0], "model": "other"})
    elif defect == "duplicate":
        verdict["models"].append(verdict["models"][0])
    elif defect == "schema":
        del verdict["reference_suspect"]
    write_verdict(case, verdict)
    if defect == "json":
        (case / "verdict.json").write_text("invalid JSON")
    assert driver.validate_verdicts(root, remove_invalid=True) == [case.name]
    assert not (case / "verdict.json").exists()
    assert not (case / "verdict.meta.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("verdict_sha256", "0" * 64),
        ("prompt_sha256", "0" * 64),
        ("judge_model_reported", ["other"]),
        ("judge_model_requested", "other"),
        ("judge_runner", None),
        ("judged_at_utc", None),
        ("judge_template_version", 1),
    ],
)
def test_new_verdicts_need_the_bound_judge_provenance(audit, field, value):
    root, case, verdict = audit
    write_verdict(case, verdict, **{field: value})
    assert driver.validate_verdicts(root) == [case.name]


def test_a_reopened_case_cannot_use_a_v1_prompt(audit):
    from policybench.judge_template import template_header

    root, case, verdict = audit
    (case / "prompt.md").write_text(template_header(1) + "\nSynthetic question.\n")
    write_verdict(case, verdict)
    assert driver.validate_verdicts(root) == [case.name]


def test_carried_verdicts_keep_the_seeds_bytes(audit):
    root, case, verdict = audit
    seed = {
        case.name: {
            "prompt_sha256": sha(case / "prompt.md"),
            "verdict_sha256": sha(case / "verdict.json"),
        }
    }
    assert driver.validate_verdicts(root, seed=seed) == []
    verdict["rationale"] += " Changed."
    write_verdict(case, verdict)
    with pytest.raises(SystemExit, match="carried-over verdicts differ"):
        driver.validate_verdicts(root, seed=seed)


@pytest.fixture
def moved_reference_audit(tmp_path):
    """scenario_031's SNAP, re-opened because the installed build moved its
    reference: Terra answered it right, so its case lists an incumbent alone.
    The seed held the case on another prompt, so its new verdict is not
    carried over."""
    from policybench.judge_template import template_header

    root = tmp_path / "audit"
    case = root / "cases" / driver.output_case(("scenario_031", "snap"))
    case.mkdir(parents=True)
    (case / "prompt.md").write_text(
        template_header(2) + "\nThe reference is the installed build's.\n"
    )
    driver.write_json(root / "schema.json", AUDIT_OUTPUT_SCHEMA)
    (root / "cases.jsonl").write_text(
        json.dumps(
            {
                "case_id": case.name,
                "wrong_models": ["claude-fable-5"],
                "parse_failure_only": False,
            }
        )
        + "\n"
    )
    verdict = _verdict(["claude-fable-5"])
    write_verdict(case, verdict)
    seed = {case.name: {"prompt_sha256": "0" * 64, "verdict_sha256": "1" * 64}}
    return SimpleNamespace(root=root, case=case, verdict=verdict, seed=seed)


def test_a_reference_only_rejudgment_with_this_releases_judge_passes(
    moved_reference_audit,
):
    s = moved_reference_audit
    assert NEW not in json.loads((s.root / "cases.jsonl").read_text())["wrong_models"]
    assert driver.validate_verdicts(s.root, seed=s.seed) == []


@pytest.mark.parametrize(
    "field,value",
    [
        # (a) another judge, requested or reported
        ("judge_model_requested", "claude-sonnet-5-5"),
        ("judge_model_reported", ["claude-sonnet-5-5"]),
        ("judge_model_reported", [driver.JUDGE_MODEL, "claude-haiku-5-5"]),
        # (b) no timestamp, or one that does not state UTC
        ("judged_at_utc", None),
        ("judged_at_utc", ""),
        ("judged_at_utc", "2026-10-26T12:00:00"),
        ("judged_at_utc", "2026-10-26T12:00:00-07:00"),
        ("judged_at_utc", "yesterday"),
        # (c) another runner, or none
        ("judge_runner", "scripts/run_audit_codex.sh"),
        ("judge_runner", None),
    ],
)
def test_a_reference_only_rejudgment_needs_this_releases_judge(
    moved_reference_audit, field, value
):
    """Terra right and an incumbent wrong on a moved reference: the new
    verdict is refused unless its sidecar shows the judge step's model,
    runner and a UTC timestamp. Before the fix the gate ran only when a new
    model was among the wrong ones."""
    s = moved_reference_audit
    write_verdict(s.case, s.verdict, **{field: value})
    if value is None:
        assert field not in json.loads((s.case / "verdict.meta.json").read_text())
    assert driver.validate_verdicts(s.root, seed=s.seed) == [s.case.name]
    assert driver.validate_verdicts(s.root, remove_invalid=True, seed=s.seed) == [
        s.case.name
    ]
    assert not (s.case / "verdict.json").exists()
    (reason,) = (s.root.parent / "rejected-verdicts" / s.case.name).glob("*/reason.txt")
    assert "Opus 5.5 provenance" in reason.read_text()
    assert field in reason.read_text()


def test_the_judge_step_runs_the_runner_the_gate_requires():
    source = (REPO / "scripts/finish_terra.py").read_text()
    assert driver.JUDGE_RUNNER == "scripts/run_audit_claude.sh"
    assert '"judge_runner": "scripts/run_audit_claude.sh"' in (
        (REPO / driver.JUDGE_RUNNER).read_text()
    )
    assert "ROOT / JUDGE_RUNNER" in source


@settings(max_examples=60, deadline=None)
@given(
    requested=st.sampled_from([driver.JUDGE_MODEL, "claude-sonnet-5-5", None]),
    reported=st.sampled_from(
        [[driver.JUDGE_MODEL], [], ["claude-sonnet-5-5"], None, driver.JUDGE_MODEL]
    ),
    runner=st.sampled_from([driver.JUDGE_RUNNER, "scripts/run_audit_codex.sh", None]),
    stamp=st.sampled_from(
        [
            "2026-10-26T12:00:00+00:00",
            "2026-10-26T12:00:00.123456+00:00",
            "2026-10-26T12:00:00Z",
            "2026-10-26T12:00:00",
            "2026-10-26T12:00:00+01:00",
            None,
            12,
        ]
    ),
)
def test_the_identity_gate_passes_exactly_this_releases_judge(
    requested, reported, runner, stamp
):
    meta = {
        "judge_model_requested": requested,
        "judge_model_reported": reported,
        "judge_runner": runner,
        "judged_at_utc": stamp,
    }
    expected = (
        requested == driver.JUDGE_MODEL
        and reported == [driver.JUDGE_MODEL]
        and runner == driver.JUDGE_RUNNER
        and isinstance(stamp, str)
        and stamp.endswith(("+00:00", "Z"))
    )
    assert (driver.judge_identity_problems(meta) == []) == expected


def triage_item(**changes):
    return {
        "scenario_id": "scenario_001",
        "variable": "snap",
        "adjudicated_failure_source": "llm_error",
        "adjudicated_failure_subtype": "thresholds_rates",
        "adjudicated_on": "2026-10-27",
        "reference_verdict": "affirmed",
        "reference_basis": "Synthetic statutory basis.",
        "reasoning": "Synthetic developer decision.",
        **changes,
    }


def triage_spec(*items, **changes):
    return {
        **real_spec(),
        "triage_adjudications": list(items),
        "triage_decided_on": "2026-10-27",
        "triage_adjudications_written_on": "2026-10-28",
        **changes,
    }


def test_the_spec_remains_open_to_later_triage_decisions():
    item = triage_item()
    assert driver.triage_items(None, triage_spec(item)) == [item]
    assert driver.triage_items(None, real_spec()) == []


@pytest.mark.parametrize(
    "changes,spec_changes",
    [
        ({"reference_verdict": "excluded"}, {}),
        ({"reference_basis": None}, {}),
        ({"reference_basis": " "}, {}),
        ({"reference_verdict": None}, {}),
        ({"adjudicated_on": "2026-10-26"}, {}),
        ({}, {"triage_decided_on": None}),
        ({"excluded_from_scoring": True}, {}),
    ],
)
def test_triage_decisions_keep_argons_record_gates(changes, spec_changes):
    with pytest.raises(SystemExit):
        driver.triage_items(None, triage_spec(triage_item(**changes), **spec_changes))


def test_triage_decisions_cannot_name_a_case_twice():
    with pytest.raises(SystemExit, match="listed twice"):
        driver.triage_items(None, triage_spec(triage_item(), triage_item()))


def test_triage_dates_keep_the_decision_day_and_written_day_separate(monkeypatch):
    spec = triage_spec(triage_item())
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    wave = driver.decision_wave((), driver.triage_items(None, spec))
    base = json.loads(
        base_blob(Path("annotations") / driver.RUN_NAME / driver.ADJUDICATIONS)
    )
    conventions = driver.release_date_conventions(base["date_conventions"], wave)
    assert "2026-10-27 wave's decisions" in conventions
    assert "written on 2026-10-28 UTC" in conventions
    del spec["triage_adjudications_written_on"]
    with pytest.raises(SystemExit, match="triage_adjudications_written_on"):
        driver.release_date_conventions(base["date_conventions"], wave)


@pytest.fixture(scope="module")
def committed_build(tmp_path_factory):
    built, explanations, actions = driver.committed_build_sources(
        tmp_path_factory.mktemp("terra-narratives")
    )
    return SimpleNamespace(built=built, explanations=explanations, actions=actions)


def load(build):
    return driver.load_build(build.built, build.explanations, build.actions)


def test_a_real_builders_build_passes_the_drivers_gates(committed_build):
    upgrade = load(committed_build)
    assert upgrade.engine_version == "policyengine-us 2.60.0"
    assert upgrade.previous_engine_version == "policyengine-us 2.41.0"
    assert set(upgrade.changed) == set(MOVED)
    assert upgrade.records == 49 and upgrade.scored_outputs == 1935
    assert not upgrade.regenerated and not upgrade.added
    assert (
        sha(committed_build.explanations)
        == driver.REFERENCE_BUILD["sha256"][driver.EXPLANATIONS_NAME]
    )
    revision = json.loads((committed_build.built / META_NAME).read_text())["revisions"][
        -1
    ]
    assert len(revision["excluded_outputs_rechecked"]) == 16
    assert revision["provenance"]["actions_sha256"] == sha(committed_build.actions)


def test_hand_corrected_narratives_never_import_a_writer_sdk(tmp_path, monkeypatch):
    import builtins

    original = builtins.__import__

    def offline_import(name, *args, **kwargs):
        if name.split(".")[0] in {"litellm", "anthropic", "openai"}:
            raise AssertionError(f"offline narratives imported {name}")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", offline_import)
    _, explanations, _ = driver.committed_build_sources(tmp_path)
    assert (
        sha(explanations) == driver.REFERENCE_BUILD["sha256"][driver.EXPLANATIONS_NAME]
    )


@pytest.mark.parametrize(
    "name", [CSV_NAME, META_NAME, EXCLUSIONS_NAME, "reference_traces.json"]
)
def test_a_build_file_off_its_pin_is_refused_before_install(
    committed_build, tmp_path, name
):
    copied = tmp_path / "tampered"
    shutil.copytree(committed_build.built, copied)
    (copied / name).write_bytes((copied / name).read_bytes() + b" ")
    bad = SimpleNamespace(**{**vars(committed_build), "built": copied})
    with pytest.raises(SystemExit, match="pin|sha256|committed"):
        load(bad)


@pytest.mark.parametrize("source", ["explanations", "actions"])
def test_narratives_and_actions_are_pinned(committed_build, tmp_path, source):
    path = tmp_path / f"changed-{source}"
    path.write_bytes(getattr(committed_build, source).read_bytes() + b" ")
    bad = SimpleNamespace(**{**vars(committed_build), source: path})
    with pytest.raises(SystemExit, match="pin|sha256|committed"):
        load(bad)


@pytest.mark.parametrize("receipt", [{}, {"references_installed": None}])
def test_a_stage_without_the_installed_build_is_refused(tmp_path, receipt):
    driver.write_json(tmp_path / "stage.json", receipt)
    with pytest.raises(SystemExit, match="install-references|installed"):
        driver.stage_upgrade(tmp_path)


def test_a_missing_stage_is_refused(tmp_path):
    with pytest.raises(SystemExit, match="stage|install-references"):
        driver.stage_upgrade(tmp_path / "missing")


@pytest.fixture
def upgrade_stage(tmp_path, monkeypatch, committed_build):
    """Full reference keys with synthetic answers and a four-case seed audit."""
    from policybench.audit import prepare_audit

    stage = tmp_path / "stage"
    bundle = stage / "publish" / driver.RUN_NAME
    us = base_references(bundle / "us")
    annotation = bundle / "annotations"
    annotation.mkdir()
    explanations = base_blob(
        Path("annotations") / driver.RUN_NAME / driver.EXPLANATIONS_NAME
    )
    (annotation / driver.EXPLANATIONS_NAME).write_bytes(explanations)
    reference = pd.read_csv(us / CSV_NAME)
    frames = []
    for model in ["incumbent-a", "incumbent-b", NEW]:
        rows = reference[driver.KEY].copy()
        rows.insert(0, "model", model)
        rows["prediction"] = reference["value"]
        rows["explanation"] = "Synthetic answer."
        rows["error"] = None
        for key in MOVED:
            mask = (rows.scenario_id == key[0]) & (rows.variable == key[1])
            rows.loc[mask, "prediction"] = -100.0
        frames.append(rows)
    pd.concat(frames, ignore_index=True).to_csv(us / "predictions.csv", index=False)
    scoring = base_references(stage / "scoring")
    grounding = tmp_path / "grounding.csv"
    grounding.write_text("scenario_id,variable,grounding\n")
    monkeypatch.setattr(driver, "GROUNDING_SHA256", sha(grounding))
    monkeypatch.setattr(driver, "reworded_since_seed", lambda: frozenset())
    monkeypatch.setattr(driver, "verify_engine_pins", lambda *a, **kw: None)
    audit = stage / "audit"
    with driver.object_strings():
        prepare_audit(us, audit, grounding_lookup={}, template_version=1)
    manifest = [
        json.loads(line) for line in (audit / "cases.jsonl").read_text().splitlines()
    ]
    assert {item["case_id"] for item in manifest} == {
        driver.output_case(k) for k in MOVED
    }
    for item in manifest:
        write_verdict(
            audit / "cases" / item["case_id"],
            _verdict(item["wrong_models"]),
            judge_template_version=1,
        )
    seed = driver.seed_digest(audit)
    monkeypatch.setattr(
        driver, "SEED_DIGEST_SHA256", sha(driver.seed_digest_text(seed).encode())
    )
    driver.write_json(
        stage / "stage.json",
        {
            "files": {
                str((us / name).relative_to(stage)): sha(us / name)
                for name in driver.REFERENCE_FILES
            },
            "seed": seed,
            "partial": False,
            "early": False,
        },
    )
    return SimpleNamespace(
        stage=stage,
        bundle=bundle,
        audit=audit,
        scoring=scoring,
        grounding=grounding,
        built=committed_build.built,
        explanations=committed_build.explanations,
        actions=committed_build.actions,
    )


def install(stage):
    driver.install_references(
        SimpleNamespace(
            stage_dir=stage.stage,
            built=stage.built,
            explanations=stage.explanations,
            actions=stage.actions,
            grounding=stage.grounding,
        )
    )


def stage_files(stage):
    return {
        str(path.relative_to(stage)): path.read_bytes()
        for path in stage.rglob("*")
        if path.is_file()
    }


def test_the_four_moved_outputs_reopen_even_when_all_answers_stay_the_same(
    upgrade_stage,
):
    s = upgrade_stage
    original = (s.bundle / "us/predictions.csv").read_bytes()
    old = {
        case.name: (case / "verdict.json").read_bytes()
        for case in (s.audit / "cases").iterdir()
    }
    install(s)
    cases = {driver.output_case(k) for k in MOVED}
    assert (s.bundle / "us/predictions.csv").read_bytes() == original
    assert set(json.loads((s.stage / "pending.json").read_text())) == cases
    assert set(driver.upgraded_cases(s.stage)) == cases
    for case in cases:
        folder = s.audit / "cases" / case
        assert not (folder / "verdict.json").exists()
        assert not (folder / "verdict.meta.json").exists()
        rejected = list((s.stage / "rejected-verdicts" / case).glob("*/verdict.json"))
        assert len(rejected) == 1
        assert rejected[0].read_bytes() == old[case]
        from policybench.judge_template import template_header

        assert (folder / "prompt.md").read_text().startswith(template_header(2))


def test_install_binds_the_exact_build_and_is_idempotent(upgrade_stage):
    s = upgrade_stage
    install(s)
    upgrade = driver.stage_upgrade(s.stage)
    assert set(upgrade.changed) == set(MOVED)
    for name in driver.UPGRADED_FILES:
        assert (s.bundle / "us" / name).read_bytes() == (s.built / name).read_bytes()
        assert (s.scoring / name).read_bytes() == (s.built / name).read_bytes()
    once = stage_files(s.stage)
    install(s)
    assert stage_files(s.stage) == once


def test_the_install_refuses_a_tampered_build_without_writing_any_stage_file(
    upgrade_stage, tmp_path
):
    s = upgrade_stage
    copied = tmp_path / "bad-build"
    shutil.copytree(s.built, copied)
    (copied / CSV_NAME).write_bytes((copied / CSV_NAME).read_bytes() + b" ")
    s.built = copied
    before = stage_files(s.stage)
    with pytest.raises(SystemExit, match="pin|sha256|committed"):
        install(s)
    assert stage_files(s.stage) == before


def test_later_steps_regate_the_installed_build(upgrade_stage):
    s = upgrade_stage
    install(s)
    path = s.stage / driver.BUILD_COPY / driver.ACTIONS_NAME
    path.write_text(path.read_text() + " ")
    with pytest.raises(SystemExit, match="installed build|pin"):
        driver.stage_upgrade(s.stage)


def test_a_stage_cannot_substitute_another_engine_for_the_bound_build(upgrade_stage):
    s = upgrade_stage
    install(s)
    receipt = json.loads((s.stage / "stage.json").read_text())
    receipt["references_installed"]["engine_version"] = "policyengine-us 2.59.0"
    driver.write_json(s.stage / "stage.json", receipt)
    with pytest.raises(SystemExit, match="installed build|engine|records"):
        driver.stage_upgrade(s.stage)


def test_a_staged_reference_cannot_differ_from_the_bound_build(upgrade_stage):
    s = upgrade_stage
    install(s)
    path = s.bundle / "us" / CSV_NAME
    path.write_text(path.read_text() + " ")
    with pytest.raises(SystemExit, match="installed build|pin"):
        driver.stage_upgrade(s.stage)


def test_the_install_changes_narratives_only_for_the_approved_outputs(upgrade_stage):
    s = upgrade_stage
    path = s.bundle / "annotations" / driver.EXPLANATIONS_NAME
    previous = path.read_bytes()
    scenarios = {
        name: (s.bundle / "us" / name).read_bytes()
        for name in ("scenarios.csv", "scenarios.csv.meta.json")
    }
    install(s)
    changed, _ = driver.explanation_changes(previous, path.read_bytes())
    assert set(changed) == set(MOVED)
    assert {
        name: (s.bundle / "us" / name).read_bytes() for name in scenarios
    } == scenarios


def test_the_install_needs_its_seed_binding(upgrade_stage):
    s = upgrade_stage
    receipt = json.loads((s.stage / "stage.json").read_text())
    del receipt["seed"]
    driver.write_json(s.stage / "stage.json", receipt)
    with pytest.raises(SystemExit, match="bind-seed"):
        install(s)


def test_the_upgrade_allowance_admits_only_its_four_changed_cases():
    cases = sorted(driver.output_case(k) for k in MOVED)
    manifest = [
        {"case_id": case, "wrong_models": ["incumbent"], "parse_failure_only": False}
        for case in cases
    ]
    prompts = {case: "a" * 64 for case in cases}
    seed = {case: "b" * 64 for case in cases}
    changes = driver.classify_prompt_changes(
        manifest, prompts, seed, frozenset(), frozenset(cases)
    )
    assert changes == {"added": [], "changed": cases, "kept": []}
    with pytest.raises(SystemExit, match="incumbent-only"):
        driver.classify_prompt_changes(
            manifest, prompts, seed, frozenset(), frozenset(cases[:-1])
        )


FABLE_USAGE = {
    "costUsd": 54.0,
    "costPerHousehold": 0.54,
    "totalTokens": 3850174,
    "latencySeconds": 97.5,
}


def stat(model, exact=50.0, **usage):
    return {
        "model": model,
        "condition": "no_tools",
        "score": exact / 100,
        "exact": exact,
        "n": 1935,
        **usage,
    }


def incumbents():
    return [stat(f"incumbent-{i:02d}", costUsd=1.25) for i in range(48)] + [
        stat("ox-alpha", costUsd=0.0, costPerHousehold=0.0),
        stat("claude-fable-5", **FABLE_USAGE),
    ]


@pytest.fixture
def scope(tmp_path, monkeypatch, committed_build):
    import policybench.dashboard_schema
    import policybench.full_run_export

    # These blobs name one immutable commit. Reuse their real git bytes so
    # property examples spend their time checking drift instead of spawning
    # hundreds of identical git reads on the shared host.
    monkeypatch.setattr(driver, "base_commit_blob", base_blob)
    bundle = tmp_path / "scope-bundle"
    base_references(bundle / "us")
    for name in driver.UPGRADED_FILES:
        shutil.copyfile(committed_build.built / name, bundle / "us" / name)
    (bundle / "us/predictions.csv").write_text("model,scenario_id,variable\n")
    (bundle / "annotations").mkdir()
    for name in ("us_audit_row_annotations.csv", "us_case_notes.csv"):
        (bundle / "annotations" / name).write_text("country\n")
    shutil.copyfile(
        committed_build.explanations, bundle / "annotations" / driver.EXPLANATIONS_NAME
    )
    upgrade = load(committed_build)
    state = SimpleNamespace(
        calls=[], references=[], stats=None, base_stats=None, installed_stats=None
    )

    def exported(*a, **kw):
        return {"countries": {"us": {"modelStats": copy.deepcopy(state.stats)}}}

    def scoped(path, live, record=None, **kwargs):
        refs = {
            name: (Path(path) / "us" / name).read_bytes()
            for name in driver.REFERENCE_FILES
        }
        state.references.append(refs)
        state.calls.append(kwargs)
        is_base = sha(refs[CSV_NAME]) == driver.BASE_REFERENCE_SHA256[CSV_NAME]
        rows = state.base_stats if is_base else state.installed_stats
        return {"countries": {"us": {"modelStats": copy.deepcopy(rows)}}}

    monkeypatch.setattr(policybench.full_run_export, "export_full_run", exported)
    monkeypatch.setattr(release_20261006, "export_payload", scoped)
    monkeypatch.setattr(
        policybench.dashboard_schema, "validate_dashboard_payload", lambda *a, **kw: []
    )

    def build(previous=None):
        previous = incumbents() if previous is None else previous
        return driver.build_payload(
            bundle, {"countries": {"us": {"modelStats": previous}}}, upgrade=upgrade
        )

    state.build = build
    state.bundle = bundle
    previous = incumbents()
    state.base_stats = copy.deepcopy(previous) + [stat(NEW)]
    state.stats = copy.deepcopy(previous) + [stat(NEW)]
    for row in state.stats:
        row["exact"] += 0.25
        row["score"] = row["exact"] / 100
    state.installed_stats = copy.deepcopy(state.stats)
    for key in FABLE_USAGE:
        del state.stats[-2][key]
    return state


def test_scope_restores_all_five_base_reference_files(scope):
    payload = scope.build()
    assert len(payload["countries"]["us"]["modelStats"]) == 51
    expected = {
        name: base_blob(SNAPSHOT_PATH / name) for name in driver.REFERENCE_FILES
    }
    assert expected in scope.references
    assert (scope.bundle / "us" / CSV_NAME).read_bytes() != expected[CSV_NAME]


def test_scope_carries_fable_usage_and_preserves_known_zero_cost(scope):
    rows = scope.build()["countries"]["us"]["modelStats"]
    fable = next(row for row in rows if row["model"] == "claude-fable-5")
    assert {key: fable[key] for key in FABLE_USAGE} == FABLE_USAGE
    assert next(row for row in rows if row["model"] == "ox-alpha")["costUsd"] == 0.0


@settings(
    max_examples=35,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(target=st.integers(0, 49), delta=st.sampled_from([1e-12, 0.25, 1.0]))
def test_base_reference_stats_must_be_byte_identical_for_every_incumbent(
    scope, target, delta
):
    original = copy.deepcopy(scope.base_stats)
    assert len(scope.build()["countries"]["us"]["modelStats"]) == 51
    scope.base_stats[target]["exact"] += delta
    with pytest.raises(SystemExit, match="incumbent modelStats drift"):
        scope.build()
    scope.base_stats = original


def test_export_refuses_drift_beyond_the_four_approved_moves(scope):
    scope.stats[3]["exact"] += 0.01
    with pytest.raises(SystemExit, match="drift|approved|installed"):
        scope.build()


@pytest.mark.parametrize("index", [0, 49, 50])
def test_every_incumbent_and_terra_keep_1935_scored_outputs(scope, index):
    scope.stats[index]["n"] = 1934
    with pytest.raises(SystemExit, match="must be scored on 1935 outputs"):
        scope.build()


@settings(max_examples=35, deadline=None)
@given(
    rows=st.lists(
        st.floats(allow_nan=False, allow_infinity=False), min_size=1, max_size=20
    )
)
def test_incumbent_drift_preserves_serialized_types_and_key_order(rows):
    previous = {
        f"m{i}": {"model": f"m{i}", "exact": value, "n": 1935}
        for i, value in enumerate(rows)
    }
    stats = copy.deepcopy(list(previous.values()))
    assert driver.incumbent_drift(stats, previous) == []
    stats[0] = dict(reversed(list(stats[0].items())))
    assert driver.incumbent_drift(stats, previous) == ["m0"]


REFERENCE = pd.read_csv(driver.SNAPSHOT / CSV_NAME)[driver.KEY]


@settings(max_examples=8, deadline=None)
@given(count=st.integers(1, 3), value=st.integers(-10000, 10000), extra=st.booleans())
def test_the_fold_adds_exactly_1984_terra_rows_on_the_reference_key_set(
    tmp_path_factory, count, value, extra
):
    import freeze_snapshot as freezer

    from policybench.fold_board import fold_board

    root = tmp_path_factory.mktemp("terra-fold")
    frames = []
    for index in range(count + 1):
        frame = REFERENCE.copy()
        frame.insert(0, "model", NEW if index == count else f"incumbent-{index}")
        frame["prediction"] = float(value)
        frame["explanation"] = 'Synthetic answer, with "quotes".'
        frame["raw_response"] = "{}"
        frame["prompt_tokens"] = 100.0
        frame["completion_tokens"] = 25.0
        frame["error"] = None
        frame["provider_resolved_model"] = frame.model
        frames.append(frame)
    base = pd.concat(frames[:-1], ignore_index=True)
    base_path = root / "base.csv"
    base.to_csv(base_path, index=False)
    addition = frames[-1]
    addition["live_calls"] = 1
    addition["cache_hit_calls"] = 0
    addition["live_elapsed_seconds"] = 1.0
    addition["elapsed_seconds"] = 1.0
    if extra:
        addition["provider_system_fingerprint"] = "fp_terra"
    addition_path = root / "terra.csv"
    addition.to_csv(addition_path, index=False)
    scoring = base_references(root / "scoring")
    result = fold_board(
        base_path, [addition_path], scoring, root / "fold", export=False
    )
    assert result["models"] == count + 1 and result["excluded"] == {}
    folded = pd.read_csv(root / "fold/us/predictions.csv", low_memory=False)
    new_rows = folded[folded.model == NEW]
    assert len(new_rows) == 1984
    assert set(new_rows[driver.KEY].itertuples(index=False, name=None)) == set(
        REFERENCE.itertuples(index=False, name=None)
    )
    assert set(addition.columns) <= set(new_rows.columns)
    for index in range(count):
        model = f"incumbent-{index}"
        assert freezer._model_prediction_rows_sha256(
            folded, model
        ) == freezer._model_prediction_rows_sha256(pd.read_csv(base_path), model)


def test_the_new_release_tag_occurs_once_in_the_drivers():
    source = (REPO / "scripts/finish_terra.py").read_text()
    assert source.count(driver.RELEASE_TAG) == 1
    assert driver.RELEASE_TAG not in (REPO / "scripts/freeze_terra.py").read_text()


# --- Judge provenance and transcripts (ported from test_finish_argon.py) ---------

ISOLATED = "us__scenario_001__snap"
UNHARDENED = "us__scenario_002__snap"
# The prompt an isolated judge's transcript shows, and its case's prompt.md.
JUDGED = "Classify these wrong answers.\n"


def _event(kind, **fields):
    return {"type": kind, **fields}


def _attachment(kind, **fields):
    return _event("attachment", attachment={"type": kind, **fields})


def _call(name, call_id, answer=None, effort="xhigh"):
    content = [{"type": "tool_use", "id": call_id, "name": name, "input": answer or {}}]
    return _event("assistant", effort=effort, message={"content": content})


def _result(call_id, error=False):
    part = {"type": "tool_result", "tool_use_id": call_id, "content": "done"}
    if error:
        part["is_error"] = True
    return _event("user", message={"content": [part]})


def _clean_transcript(effort="xhigh", prompt=JUDGED, models=(NEW,)):
    """An isolated judge's transcript, shaped like the runner's real ones: its
    one accepted StructuredOutput call answers the verdict the provenance
    fixture writes, every assistant turn at ``effort``."""
    return [
        _event("user", message={"content": prompt}),
        _attachment("environment", snapshot={"isGitRepo": False}),
        _attachment("model"),
        _attachment("session_context", context={}),
        _attachment("date"),
        _attachment("prompt_snapshot"),
        _event("assistant", effort=effort, message={"content": [{"type": "text"}]}),
        _call("StructuredOutput", "call-1", _verdict(list(models)), effort=effort),
        _attachment("structured_output"),
        _result("call-1"),
    ]


def _write_transcript(case, events):
    (case / "claude.transcript.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )


# An isolated judge's sidecar fields: a token login on a lane whose account
# it declares, which the public record withholds.
ISOLATED_SIDECAR = {
    "judge_effort": "xhigh",
    "judge_isolation": {"tools": "none (--tools '')"},
    "judge_auth": {"method": "oauth_token", "account": None, "org": None},
    "judge_account_declared": "claude:lane@example.org (pb-judge)",
}
WITHHELD = "<account withheld>"


def _record_entry(case: Path, group: str) -> dict:
    """The entry a true record gives a staged verdict: its hashes, its group
    and isolation, and its sidecar's fields with addresses withheld."""
    meta = json.loads((case / "verdict.meta.json").read_text())
    return {
        "case_id": case.name,
        "group": group,
        "isolated": "judge_isolation" in meta,
        "judge_account_declared": (
            meta["judge_account_declared"].replace("lane@example.org", WITHHELD)
            if "judge_account_declared" in meta
            else None
        ),
        "judge_effort": meta.get("judge_effort"),
        "judge_model_reported": meta["judge_model_reported"],
        "judged_at_utc": meta["judged_at_utc"],
        "judge_template_version": meta.get("judge_template_version"),
        "verdict_sha256": driver.digest(case / "verdict.json"),
        "prompt_sha256": driver.digest(case / "prompt.md"),
    }


def _provenance_record(entries: list[dict], note: str | None = None):
    """A record of ``entries``; its note is the one they give unless ``note``."""
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["group"]] = counts.get(entry["group"], 0) + 1
    if note is None:
        note = driver.provenance_note(entries)
    return {"note": note, "counts": counts, "verdicts": entries}


GROUPS = {ISOLATED: "isolated: pb-judge", UNHARDENED: "unhardened: in-repo runner"}


@pytest.fixture
def provenance(tmp_path):
    """Two new verdicts, one isolated and one not, and a true record of both."""
    cases = tmp_path / "audit/cases"
    entries = []
    for name, isolated in ((ISOLATED, True), (UNHARDENED, False)):
        case = cases / name
        case.mkdir(parents=True)
        (case / "prompt.md").write_text(JUDGED)
        write_verdict(case, _verdict([NEW]), **(ISOLATED_SIDECAR if isolated else {}))
        _write_transcript(case, _clean_transcript())
        entries.append(_record_entry(case, GROUPS[name]))
    record = tmp_path / "judge_provenance.json"

    def verify(edit=lambda entries: None, edit_record=lambda record: None):
        edited = copy.deepcopy(entries)
        edit(edited)
        written = _provenance_record(edited)
        edit_record(written)
        record.write_text(json.dumps(written))
        driver.verify_judge_provenance(cases, frozenset({ISOLATED, UNHARDENED}), record)

    return cases, verify


def test_the_judge_provenance_record_describes_the_staged_verdicts(provenance):
    _, verify = provenance
    verify()


def test_the_runners_attachment_allowlist_is_the_gates():
    script = (driver.ROOT / "scripts/run_audit_claude.sh").read_text()
    line = next(line for line in script.splitlines() if line.startswith("ATTACHMENTS="))
    assert set(line.split('"')[1].split(",")) == driver.JUDGE_ATTACHMENTS


@pytest.mark.parametrize("case", [ISOLATED, UNHARDENED])
def test_a_verdict_whose_isolation_disagrees_with_the_record_is_refused(
    provenance, case
):
    _, verify = provenance

    def flip(entries):
        entry = next(e for e in entries if e["case_id"] == case)
        entry["isolated"] = not entry["isolated"]

    with pytest.raises(SystemExit, match=f"{case}: the record says isolated"):
        verify(flip)


def test_a_sidecar_that_drops_its_isolation_disagrees_with_the_record(provenance):
    cases, verify = provenance
    case = cases / ISOLATED
    meta = json.loads((case / "verdict.meta.json").read_text())
    del meta["judge_isolation"]
    (case / "verdict.meta.json").write_text(json.dumps(meta))
    with pytest.raises(SystemExit, match="sidecar lacks judge_isolation"):
        verify()


@pytest.mark.parametrize(
    "edit, problem",
    [
        (lambda e: e.pop(), "does not list each re-opened case once"),
        (lambda e: e.append(dict(e[0])), "does not list each re-opened case once"),
        (lambda e: e[0].update(verdict_sha256="0" * 64), "names another verdict"),
        (lambda e: e[1].update(prompt_sha256="0" * 64), "names another prompt"),
    ],
)
def test_the_record_must_list_each_staged_new_verdict_once(provenance, edit, problem):
    _, verify = provenance
    with pytest.raises(SystemExit, match=problem):
        verify(edit)


def _entry(case):
    return lambda entries: next(e for e in entries if e["case_id"] == case)


# Each sidecar field the record copies, rewritten in one entry.
SIDECAR_FIELD_EDITS = {
    "judge_effort": (ISOLATED, "max"),
    "judge_model_reported": (UNHARDENED, ["claude-opus-5"]),
    "judged_at_utc": (ISOLATED, "2026-10-09T08:00:00+00:00"),
    "judge_account_declared": (ISOLATED, f"claude:{WITHHELD} (another lane)"),
    "judge_account_declared_unhardened": (UNHARDENED, "a lane it never ran on"),
    "judge_template_version": (ISOLATED, 1),
}


@pytest.mark.parametrize("edit", sorted(SIDECAR_FIELD_EDITS))
def test_each_entrys_fields_must_be_its_sidecars(provenance, edit):
    _, verify = provenance
    case, value = SIDECAR_FIELD_EDITS[edit]
    field = edit.removesuffix("_unhardened")

    def rewrite(entries):
        _entry(case)(entries)[field] = value

    problem = f"{case}: its {field} .* is not the sidecar's"
    with pytest.raises(SystemExit, match=problem):
        verify(rewrite)


def test_the_record_withholds_the_sidecars_address_and_names_none(provenance):
    """The entry carries the sidecar's declaration with its address withheld;
    the address itself, there or anywhere else in the record, is refused."""
    _, verify = provenance

    def declared(entries):
        _entry(ISOLATED)(entries)["judge_account_declared"] = (
            "claude:lane@example.org (pb-judge)"
        )

    with pytest.raises(SystemExit, match=r"is public and names .*e-mail address"):
        verify(declared)

    def in_note(record):
        record["note"] += " The lane is lane@example.org."

    with pytest.raises(SystemExit, match=r"is public and names .*record\.note"):
        verify(edit_record=in_note)

    def in_group(entries):
        for entry in entries:
            entry["group"] = entry["group"].replace("pb-judge", "judge@example.org")

    with pytest.raises(SystemExit, match="is public and names"):
        verify(in_group)


# The fixture record's true counts: one entry in each group.
GROUP_COUNTS = {group: 1 for group in GROUPS.values()}


@pytest.mark.parametrize(
    "counts", [{}, {"isolated: pb-judge": 2}, {**GROUP_COUNTS, "extra": 0}]
)
def test_the_counts_must_be_the_tally_of_the_entries_groups(provenance, counts):
    _, verify = provenance
    with pytest.raises(SystemExit, match="counts .* are not the tally"):
        verify(edit_record=lambda record: record.update(counts=counts))


@pytest.mark.parametrize(
    "auth", [None, {"method": "claude.ai", "account": "8f0c"}, {"method": None}]
)
def test_an_isolated_verdict_needs_a_token_login(provenance, auth):
    cases, verify = provenance
    meta_path = cases / ISOLATED / "verdict.meta.json"
    meta = json.loads(meta_path.read_text())
    meta.pop("judge_auth")
    if auth is not None:
        meta["judge_auth"] = auth
    meta_path.write_text(json.dumps(meta))
    problem = f"{ISOLATED}: the sidecar does not record a token login"
    with pytest.raises(SystemExit, match=problem):
        verify()


def test_the_record_and_its_entries_carry_only_checked_keys(provenance):
    _, verify = provenance

    def claim(entries):
        _entry(ISOLATED)(entries)["environment"] = "allowlisted"

    with pytest.raises(SystemExit, match=f"{ISOLATED}: the entry has keys"):
        verify(claim)
    with pytest.raises(SystemExit, match="has keys .*; expected"):
        verify(edit_record=lambda record: record.update(isolation="all allowlisted"))


def test_only_an_isolated_entrys_group_says_isolated(provenance):
    _, verify = provenance

    def regroup(entries):
        _entry(UNHARDENED)(entries)["group"] = "isolated: in-repo runner"

    with pytest.raises(SystemExit, match=f"{UNHARDENED}: its group .* disagrees"):
        verify(regroup)


def _read_call(events):
    events[-3:-3] = [_call("Read", "call-0"), _result("call-0")]


def _second_answer(events):
    events += [_call("StructuredOutput", "call-2"), _result("call-2")]


def _no_answer(events):
    del events[7:10]


def _user(content, **fields):
    return _event("user", message={"content": content}, **fields)


def _forged_answer(events):
    """A StructuredOutput call no assistant turn made, and its "result"."""
    content = [{"type": "tool_use", "id": "call-9", "name": "StructuredOutput"}]
    events += [
        _event("system", message={"content": content}),
        _user([{"type": "tool_result", "tool_use_id": "call-9", "content": "A hint."}]),
    ]


TRANSCRIPT_DEFECTS = {
    "read_tool_call": (_read_call, r"tool calls \['Read'\]"),
    "no_answer": (_no_answer, "0 accepted StructuredOutput"),
    "two_answers": (_second_answer, "2 accepted StructuredOutput"),
    "account_email": (
        lambda e: e[3].update(_attachment("session_context", context={"userEmail": 1})),
        r"session context carrying \['userEmail'\]",
    ),
    "credential_org": (
        lambda e: e.append(_attachment("credential_org")),
        "'credential_org' attachment",
    ),
    "skill_listing": (
        lambda e: e.append(_attachment("skill_listing")),
        "'skill_listing' attachment",
    ),
    "git_repository": (
        lambda e: e[1].update(_attachment("environment", snapshot={"isGitRepo": True})),
        "inside a git repository",
    ),
    "other_effort": (lambda e: e[6].update(effort="max"), "effort 'max'"),
    "advisor": (lambda e: e[6].update(advisorModel="m"), "advisor model"),
    "not_an_event": (lambda e: e.append("{"), "not an event"),
    # The prompt binding: one user text message, prompt.md's, and otherwise
    # only the results of the judge's own StructuredOutput calls.
    "other_prompt": (
        lambda e: e[0].update(_user("Classify another case.\n")),
        "its user message is not prompt.md",
    ),
    "no_prompt": (lambda e: e.pop(0), "0 user text messages"),
    "second_text": (
        lambda e: e.insert(7, _user("Also weigh this hint.")),
        "2 user text messages",
    ),
    "nudge_not_meta": (
        lambda e: e.insert(7, _user(driver.JUDGE_PROMPT_NUDGE)),
        "2 user text messages",
    ),
    "meta_text_part": (
        lambda e: e.insert(
            7, _user([{"type": "text", "text": "A hint."}], isMeta=True)
        ),
        "not a StructuredOutput call's result",
    ),
    "stray_result": (
        lambda e: e.append(_user([{"type": "tool_result", "tool_use_id": "call-8"}])),
        "not a StructuredOutput call's result",
    ),
    "forged_answer": (_forged_answer, "not a StructuredOutput call's result"),
    # The verdict: the one accepted answer must be verdict.json.
    "other_answer": (
        lambda e: e[7]["message"]["content"][0]["input"].update(rationale="Other."),
        "its accepted StructuredOutput answer is not verdict.json",
    ),
    # Only the event types the isolated transcripts carry.
    "unlisted_event": (
        lambda e: e.append(_event("progress", data={"phase": "thinking"})),
        "an event of type 'progress'",
    ),
    # No account data outside the prompt's own text and the judge's words.
    "email_in_system_prompt": (
        lambda e: e[5].update(
            _attachment("prompt_snapshot", systemPrompt=["Mail max@example.org."])
        ),
        r"an e-mail address at line 6\.attachment\.systemPrompt\[0\]",
    ),
    "account_key_in_environment": (
        lambda e: e[1].update(
            _attachment(
                "environment",
                snapshot={"isGitRepo": False, "identity": {"accountUuid": "8f0c"}},
            )
        ),
        r"key line 2\.attachment\.snapshot\.identity\.accountUuid",
    ),
    "email_beside_the_prompt": (
        lambda e: e[0].update(userEmail="max@example.org"),
        r"key line 1\.userEmail",
    ),
    "account_key_beside_the_judges_words": (
        lambda e: e[6].update(organizationUuid="org-1"),
        r"key line 7\.organizationUuid",
    ),
    "email_in_queue_operation": (
        lambda e: e.insert(
            0, _event("queue-operation", operation="enqueue", content="max@x.org")
        ),
        r"an e-mail address at line 1\.content",
    ),
    "git_status_key": (
        lambda e: e[4].update(_attachment("date", gitStatus="M a.py")),
        r"key line 5\.attachment\.gitStatus",
    ),
}


@pytest.mark.parametrize("defect", sorted(TRANSCRIPT_DEFECTS))
def test_an_isolated_verdict_whose_transcript_fails_the_runners_checks_is_refused(
    provenance, defect
):
    cases, verify = provenance
    edit, problem = TRANSCRIPT_DEFECTS[defect]
    events = _clean_transcript()
    edit(events)
    _write_transcript(cases / ISOLATED, events)
    with pytest.raises(SystemExit, match=f"{ISOLATED}: .*{problem}"):
        verify()


def test_an_isolated_verdict_needs_its_transcript(provenance):
    cases, verify = provenance
    (cases / ISOLATED / "claude.transcript.jsonl").unlink()
    with pytest.raises(SystemExit, match="no transcript"):
        verify()


def test_an_answer_the_schema_refused_and_the_judge_gave_again_passes(provenance):
    cases, verify = provenance
    events = _clean_transcript()
    events[7:7] = [_call("StructuredOutput", "call-0"), _result("call-0", error=True)]
    _write_transcript(cases / ISOLATED, events)
    verify()


def test_claude_codes_own_structured_output_nudge_passes(provenance):
    """The judge answered in text, Claude Code nudged it (an isMeta user
    message) and it called StructuredOutput."""
    cases, verify = provenance
    events = _clean_transcript()
    events.insert(7, _user(driver.JUDGE_PROMPT_NUDGE, isMeta=True))
    _write_transcript(cases / ISOLATED, events)
    verify()


def test_an_address_in_the_prompt_or_the_judges_own_words_passes(provenance):
    """The account-data rule reads neither the judged prompt's own text nor
    the judge's turns."""
    cases, verify = provenance
    case = cases / ISOLATED
    prompt = "Classify these wrong answers; the filer wrote to irs@example.gov.\n"
    (case / "prompt.md").write_text(prompt)
    events = _clean_transcript()
    events[0] = _user(prompt)
    events[6]["message"]["content"] = [{"type": "text", "text": "irs@example.gov"}]
    _write_transcript(case, events)

    def follow(entries):
        entry = next(e for e in entries if e["case_id"] == ISOLATED)
        entry["prompt_sha256"] = driver.digest(case / "prompt.md")

    verify(follow)


def test_the_runners_event_types_are_the_gates():
    script = (driver.ROOT / "scripts/run_audit_claude.sh").read_text()
    line = next(line for line in script.splitlines() if line.startswith("EVENT_TYPES="))
    assert set(line.split('"')[1].split(",")) == driver.JUDGE_EVENT_TYPES


def test_the_runners_account_patterns_are_the_gates():
    script = (driver.ROOT / "scripts/run_audit_claude.sh").read_text()
    assert driver.ACCOUNT_KEY.flags & re.IGNORECASE
    assert f'account_key = re.compile(r"{driver.ACCOUNT_KEY.pattern}", re.I)' in script
    assert f'email_address = re.compile(r"{driver.EMAIL_ADDRESS.pattern}")' in script


def test_the_runners_nudge_is_the_gates():
    script = (driver.ROOT / "scripts/run_audit_claude.sh").read_text()
    line = next(
        line for line in script.splitlines() if line.startswith("PROMPT_NUDGE=")
    )
    assert line == f'PROMPT_NUDGE="{driver.JUDGE_PROMPT_NUDGE}"'


# The two problem messages this driver words differently from the GPT-6.1 Sol
# driver's port (which tests/test_run_audit_claude.py compares with the
# runner); the differential tests below read them in that driver's words.
TERRA_WORDING = (
    (
        re.compile(r" accepted StructuredOutput calls; exactly 1 is required$"),
        " accepted StructuredOutput calls, not 1",
    ),
    (
        re.compile(r" user text messages; only the prompt is allowed$"),
        " user text messages, not the prompt alone",
    ),
)


def _in_gpt61sol_words(problems):
    if not isinstance(problems, list):
        return problems
    worded = []
    for problem in problems:
        for pattern, replacement in TERRA_WORDING:
            problem = pattern.sub(replacement, problem)
        worded.append(problem)
    return worded


def _both_gates(path: Path, effort, prompt: bytes, verdict) -> tuple:
    import finish_gpt61sol as gpt61sol

    results = []
    for module in (driver, gpt61sol):
        try:
            results.append(module.transcript_problems(path, effort, prompt, verdict))
        except Exception as error:  # noqa: BLE001 - compared, not swallowed
            results.append((type(error).__name__, str(error)))
    return (_in_gpt61sol_words(results[0]), results[1])


def test_this_drivers_transcript_gate_is_the_gpt61sol_drivers():
    """tests/test_run_audit_claude.py compares the runner with the GPT-6.1 Sol
    driver's Python port of its transcript checks, so this driver's port must
    be that one: the same helpers and constants and, on every defect the tests
    name, the same problems (two of them worded differently)."""
    import finish_gpt61sol as gpt61sol

    for name in ("account_data", "outside_the_judge", "withhold_addresses"):
        assert inspect.getsource(getattr(driver, name)) == inspect.getsource(
            getattr(gpt61sol, name)
        ), name
    for name in (
        "JUDGE_ATTACHMENTS",
        "JUDGE_EVENT_TYPES",
        "JUDGE_PROMPT_NUDGE",
        "JUDGE_PROVENANCE_KEYS",
        "WITHHELD_ADDRESS",
        "JUDGE_MODEL",
    ):
        assert getattr(driver, name) == getattr(gpt61sol, name), name
    assert driver.JUDGE_SIDECAR_FIELDS == (
        *gpt61sol.JUDGE_SIDECAR_FIELDS,
        "judge_template_version",
    )
    assert driver.JUDGE_PROVENANCE_ENTRY_KEYS == (
        gpt61sol.JUDGE_PROVENANCE_ENTRY_KEYS | {"judge_template_version"}
    )
    for name in ("ACCOUNT_KEY", "EMAIL_ADDRESS"):
        ours, theirs = getattr(driver, name), getattr(gpt61sol, name)
        assert (ours.pattern, ours.flags) == (theirs.pattern, theirs.flags), name
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "claude.transcript.jsonl"
        for defect in [None, *sorted(TRANSCRIPT_DEFECTS)]:
            events = _clean_transcript()
            if defect is not None:
                TRANSCRIPT_DEFECTS[defect][0](events)
            _write_transcript(path.parent, events)
            ours, theirs = _both_gates(path, "xhigh", JUDGED.encode(), _verdict([NEW]))
            assert ours == theirs, defect
            # The comparison is not vacuous: each named defect is a problem.
            assert (ours == []) == (defect is None), defect


JSON_LEAVES = st.none() | st.booleans() | st.integers() | st.text(max_size=3)
JSON_LEAVES |= st.floats(allow_nan=False, allow_infinity=False)
JSON_VALUES = st.recursive(
    JSON_LEAVES,
    lambda inner: (
        st.lists(inner, max_size=3)
        | st.dictionaries(st.sampled_from("abcd"), inner, max_size=3)
    ),
    max_leaves=12,
)
JSON_EVENT = st.fixed_dictionaries(
    {"type": st.sampled_from(sorted(driver.JUDGE_EVENT_TYPES | {"system", "other"}))},
    optional={
        "message": st.fixed_dictionaries(
            {},
            optional={
                "content": st.text(max_size=12)
                | st.lists(
                    st.fixed_dictionaries(
                        {
                            "type": st.sampled_from(
                                ["text", "tool_use", "tool_result", "server_tool_use"]
                            )
                        },
                        optional={
                            "id": st.sampled_from(["c1", "c2"]),
                            "tool_use_id": st.sampled_from(["c1", "c2"]),
                            "name": st.sampled_from(["StructuredOutput", "Read"]),
                            "input": JSON_VALUES,
                            "is_error": st.booleans(),
                        },
                    ),
                    max_size=3,
                )
            },
        ),
        "attachment": st.fixed_dictionaries(
            {"type": st.sampled_from(sorted(driver.JUDGE_ATTACHMENTS | {"skill"}))},
            optional={"context": JSON_VALUES, "snapshot": JSON_VALUES},
        ),
        "effort": st.sampled_from(["xhigh", "max"]),
        "isMeta": st.booleans(),
        "userEmail": st.just("a@b.org"),
    },
)


@settings(max_examples=200, deadline=None)
@given(
    events=st.lists(JSON_EVENT | JSON_VALUES, max_size=6),
    defects=st.lists(st.sampled_from(sorted(TRANSCRIPT_DEFECTS)), max_size=3),
    effort=st.none() | st.just("xhigh"),
)
def test_the_transcript_gates_agree_on_any_transcript(events, defects, effort):
    """Differential: on arbitrary event lists, and on any combination of the
    named defects, this driver's transcript checks give the GPT-6.1 Sol
    driver's answer."""
    clean = _clean_transcript()
    for defect in defects:
        try:
            TRANSCRIPT_DEFECTS[defect][0](clean)
        except (IndexError, KeyError, TypeError, AttributeError):
            pass
    with tempfile.TemporaryDirectory() as scratch:
        for lines in (events, clean, clean + events):
            path = Path(scratch) / "claude.transcript.jsonl"
            path.write_text("".join(json.dumps(line) + "\n" for line in lines))
            ours, theirs = _both_gates(path, effort, JUDGED.encode(), _verdict([NEW]))
            assert ours == theirs


def test_a_prompt_changed_after_its_judge_ran_is_refused(provenance):
    """A prompt.md replaced after judging, with the record following it, still
    disagrees with the prompt the judge's transcript shows."""
    cases, verify = provenance
    (cases / ISOLATED / "prompt.md").write_text("Classify these, and one more.\n")

    def follow(entries):
        entry = next(e for e in entries if e["case_id"] == ISOLATED)
        entry["prompt_sha256"] = driver.digest(cases / ISOLATED / "prompt.md")

    with pytest.raises(SystemExit, match=f"{ISOLATED}: its user message is not"):
        verify(follow)


def test_an_unhardened_verdicts_transcript_is_not_held_to_isolation(provenance):
    cases, verify = provenance
    events = _clean_transcript()
    _read_call(events)
    _write_transcript(cases / UNHARDENED, events)
    verify()


def test_the_committed_provenance_record_is_public_and_tallied():
    """Once committed: the record is json.dumps(indent=1), ASCII-escaped, with
    a trailing newline; it names no e-mail address, its counts are the tally
    of its entries' groups, and its note is the one its entries give."""
    if not driver.JUDGE_PROVENANCE.is_file():
        pytest.skip("docs/terra/judge_provenance.json is not written yet")
    text = driver.JUDGE_PROVENANCE.read_text()
    record = json.loads(text)
    assert text == json.dumps(record, indent=1) + "\n" and text.isascii()
    assert not driver.EMAIL_ADDRESS.search(text)
    groups = [entry["group"] for entry in record["verdicts"]]
    assert record["counts"] == {group: groups.count(group) for group in groups}
    assert record["note"] == driver.provenance_note(record["verdicts"])


# --- The generated provenance note (review r1, finding 2) ------------------------

# Claims release 20261014's note made about its own run, which no Terra record
# carries: its one login, its effort, its schedule and its retries.
INHERITED_CLAIMS = (
    "two at a time",
    "one at a time",
    "dropped network connection",
    "judged again",
    "Max's second setup-token login",
    "2026-09-30 opt-in",
    "All ran on",
    "Scores do not depend",
)


def _provenance_case(cases: Path, case_id: str, account: str, effort: str) -> Path:
    """An isolated, re-opened case whose sidecar declares ``account`` and
    records ``effort``, with the transcript the runner leaves at that effort."""
    case = cases / case_id
    case.mkdir(parents=True)
    (case / "prompt.md").write_text(JUDGED)
    write_verdict(
        case,
        _verdict([NEW]),
        judge_effort=effort,
        judge_isolation={"tools": "none (--tools '')"},
        judge_auth={"method": "oauth_token", "account": None, "org": None},
        judge_account_declared=account,
    )
    _write_transcript(case, _clean_transcript(effort=effort))
    return case


def _generated_record(tmp_path: Path, runs: list[tuple[str, str]]) -> dict:
    """The record write_judge_provenance writes for one case per (account,
    effort) in ``runs``, checked by the export gate."""
    cases = tmp_path / "audit/cases"
    names = []
    for index, (account, effort) in enumerate(runs):
        names.append(f"us__scenario_{index:03d}__snap")
        _provenance_case(cases, names[-1], account, effort)
    rejudged = frozenset(names)
    record = json.loads(
        json.dumps(driver.judge_provenance_record(cases, rejudged), sort_keys=True)
    )
    path = tmp_path / "judge_provenance.json"
    path.write_text(json.dumps(record, indent=1) + "\n")
    driver.verify_judge_provenance(cases, rejudged, path)
    return record


LANE_10 = "claude:max@farness.ai (subfleet lane claude-10)"
LANE_18 = "claude:max@axiom.org (subfleet lane claude-18)"
SETUP_TOKEN = "claude setup-token login (token sha256 6a6daf56361b), Max 2026-09-30"


@pytest.mark.parametrize("account", [LANE_10, LANE_18, SETUP_TOKEN])
@pytest.mark.parametrize("effort", ["high", "xhigh", "max"])
def test_the_note_states_only_what_the_runs_sidecars_record(tmp_path, account, effort):
    """A run on any listed account, at the effort AUDIT_EFFORT set, gets a note
    whose every claim its sidecars support: no other login, effort, schedule
    or retry history."""
    record = _generated_record(tmp_path, [(account, effort)])
    note = record["note"]
    assert f"Effort recorded: {effort} (1)." in note
    assert f"Judge model reported: {driver.JUDGE_MODEL} (1)." in note
    assert f"Judge template: v{driver.JUDGE_TEMPLATE_VERSION} (1)." in note
    assert "Isolation: isolated (1)." in note
    assert record["counts"] == {driver.PROVENANCE_GROUPS[account]: 1}
    for claim in INHERITED_CLAIMS:
        assert claim not in note, claim
    others = {"low", "medium", "high", "xhigh", "max"} - {effort}
    assert (
        not {word for word in re.findall(r"[a-z]+", note.split("Effort recorded:")[1])}
        & others
    )
    assert "setup-token" not in note and "lane" not in note
    assert not driver.EMAIL_ADDRESS.search(json.dumps(record))


def test_a_mixed_run_is_tallied_by_effort_and_login(tmp_path):
    record = _generated_record(
        tmp_path, [(LANE_10, "high"), (SETUP_TOKEN, "xhigh"), (LANE_10, "xhigh")]
    )
    assert "Effort recorded: high (1), xhigh (2)." in record["note"]
    assert record["counts"] == {
        "isolated: subfleet lane claude-10": 2,
        "isolated: setup-token 2": 1,
    }


@pytest.mark.parametrize(
    "note",
    [
        # Release 20261014's note, its claims about that run kept.
        "Provenance of the new Opus 5.5 judge verdicts in the GPT-6.1 Terra stage: "
        "cases re-opened by Terra or the installed reference build. All ran on "
        "Max's second setup-token login (2026-09-30 opt-in), at effort xhigh, "
        "two at a time and then one at a time.",
        "How each was judged.",
    ],
)
def test_a_note_its_entries_do_not_give_is_refused(provenance, note):
    _, verify = provenance
    with pytest.raises(SystemExit, match="note is not the one its entries give"):
        verify(edit_record=lambda record: record.update(note=note))


def test_an_edited_effort_in_the_note_is_refused(tmp_path):
    record = _generated_record(tmp_path, [(LANE_10, "high")])
    cases = tmp_path / "audit/cases"
    record["note"] = record["note"].replace("high (1)", "xhigh (1)")
    path = tmp_path / "judge_provenance.json"
    path.write_text(json.dumps(record))
    with pytest.raises(SystemExit, match="note is not the one its entries give"):
        driver.verify_judge_provenance(
            cases, frozenset({"us__scenario_000__snap"}), path
        )


def _phrase_counts(note: str, label: str, after: str) -> dict[str, int]:
    text = note.split(f"{label}: ")[1].split(f". {after}")[0]
    if text == "none":
        return {}
    pairs = re.findall(r"(.+?) \((\d+)\)(?:, |$)", text)
    return {value: int(count) for value, count in pairs}


@settings(max_examples=150, deadline=None)
@given(
    entries=st.lists(
        st.fixed_dictionaries(
            {
                "judge_effort": st.sampled_from(
                    [None, "low", "medium", "high", "xhigh", "max"]
                ),
                "judge_template_version": st.sampled_from([None, 1, 2]),
                "isolated": st.booleans(),
                "judge_model_reported": st.sampled_from(
                    [[driver.JUDGE_MODEL], ["claude-sonnet-5-5"], [], None]
                ),
            }
        ),
        max_size=8,
    )
)
def test_the_note_round_trips_to_the_entries_tallies(entries):
    """Every tally the note states is its entries' tally, and the note names
    the count of entries: no value appears that no entry records."""
    note = driver.provenance_note(entries)
    assert note == driver.provenance_note(copy.deepcopy(entries))
    assert note.startswith(f"Provenance of the {len(entries)} new judge verdicts")
    efforts = Counter(
        e["judge_effort"] if e["judge_effort"] else "none recorded" for e in entries
    )
    assert _phrase_counts(note, "Effort recorded", "Judge template") == efforts
    templates = Counter(
        f"v{e['judge_template_version']}"
        if e["judge_template_version"] is not None
        else "none recorded"
        for e in entries
    )
    assert _phrase_counts(note, "Judge template", "Isolation") == templates
    isolation = Counter(
        "isolated" if e["isolated"] else "not isolated" for e in entries
    )
    assert _phrase_counts(note, "Isolation", "An isolated") == isolation
    models = Counter(
        " and ".join(e["judge_model_reported"])
        if e["judge_model_reported"]
        else "none reported"
        for e in entries
    )
    assert _phrase_counts(note, "Judge model reported", "Effort recorded") == models


# --- Stage isolation, CLI modes and resume (ported from test_finish_argon.py) ----


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setattr(driver, "ROOT", root)
    return root


RESUMED_STEPS = [
    "export",
    "triage",
    "judge",
    "provenance",
    "install-exclusions",
    "adjudicate-exclusions",
    "bind-seed",
]
# What a rehearsal stage.json may carry in place of each flag's False.
REHEARSAL_FLAGS = [True, "missing", None, 0, 1, "false", "False", [], {}]


@pytest.mark.parametrize("step", RESUMED_STEPS)
@pytest.mark.parametrize("field", ["partial", "early"])
@pytest.mark.parametrize("value", REHEARSAL_FLAGS, ids=repr)
def test_an_early_or_partial_stage_cannot_resume_into_release(
    workspace, monkeypatch, field, step, value
):
    """Each later step refuses a stage.json whose early or partial flag is not
    recorded as False, before it reads anything else of the stage."""
    for name in ("stage_upgrade", "triage", "export", "judge", "bind_seed"):
        monkeypatch.setattr(driver, name, lambda *a, n=name: pytest.fail(f"{n} ran"))
    stage = workspace / "results/local/stage"
    stage.mkdir(parents=True)
    receipt = {"partial": False, "early": False, "files": {}}
    if value == "missing":
        del receipt[field]
    else:
        receipt[field] = value
    (stage / "stage.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="early/partial stage cannot become a release"):
        driver.main(["--stage-dir", str(stage), "--step", step])


@pytest.mark.parametrize(
    "receipt, ok",
    [
        ({"early": False, "partial": False}, True),
        ({"early": False, "partial": False, "files": {}}, True),
        ({"early": True, "partial": False}, False),
        ({"early": False, "partial": True}, False),
        ({"early": False}, False),
        ({"partial": False}, False),
        ({"early": 0, "partial": 0}, False),
        ([], False),
        (None, False),
    ],
)
def test_require_release_stage_accepts_only_two_false_flags(receipt, ok):
    if ok:
        driver.require_release_stage(receipt)
    else:
        with pytest.raises(SystemExit, match="cannot become a release"):
            driver.require_release_stage(receipt)


@pytest.mark.parametrize("relation", ["same", "parent", "child"])
def test_stage_must_not_overlap_any_input(workspace, relation):
    stage = workspace / "results/local/stage"
    source = {"same": stage, "parent": stage.parent, "child": stage / "source"}[
        relation
    ]
    with pytest.raises(SystemExit, match="overlaps input"):
        driver.validate_stage_path(stage, [source])


@pytest.mark.parametrize("relative", ["app/src", "paper/snapshot", "results/local"])
def test_stage_must_be_a_scratch_subdirectory(workspace, relative):
    with pytest.raises(SystemExit, match="stage-dir must be below"):
        driver.validate_stage_path(workspace / relative, [])


@pytest.mark.parametrize("depth", ["top", "nested"])
def test_stage_cannot_contain_symlink_to_a_live_file(workspace, depth):
    stage = workspace / "results/local/stage"
    folder = stage if depth == "top" else stage / "publish" / driver.RUN_NAME / "us"
    folder.mkdir(parents=True)
    (folder / "predictions.csv").symlink_to(workspace / "live.csv")
    with pytest.raises(SystemExit, match="symlink in stage-dir"):
        driver.validate_stage_path(stage, [])


def test_disjoint_scratch_stage_is_allowed(workspace):
    driver.validate_stage_path(
        workspace / "results/local/stage", [workspace / "results/local/inputs"]
    )


@pytest.mark.parametrize(
    "source", ["snapshot", "annotations", "runs", "seed", "grounding"]
)
def test_main_refuses_a_stage_inside_any_read_only_input(workspace, source):
    """main passes every read-only source to the overlap check before any
    step reads the stage."""
    inputs = workspace / "results/local/inputs"
    stage = inputs / "stage"
    options = {
        "snapshot": [],
        "annotations": [],
        "runs": ["--runs-root", str(inputs)],
        "seed": ["--audit-seed", str(inputs)],
        "grounding": ["--grounding", str(inputs)],
    }[source]
    if source in ("snapshot", "annotations"):
        stage = (driver.SNAPSHOT if source == "snapshot" else driver.ANNOTATIONS) / "s"
    with pytest.raises(SystemExit, match="overlaps input|stage-dir must be below"):
        driver.main(["--stage-dir", str(stage), "--step", "triage", *options])


EARLY_STEPS = [
    "judge",
    "triage",
    "export",
    "provenance",
    "bind-seed",
    "install-exclusions",
    "adjudicate-exclusions",
]


@pytest.mark.parametrize(
    "options, message",
    [
        (["--partial"], "--partial requires --early"),
        (["--partial", "--step", "export"], "--partial requires --early"),
        *[
            (["--early", "--step", step], "--early only applies to prepare")
            for step in EARLY_STEPS
        ],
        (
            ["--early", "--step", "install-references", "--grounding", "g.csv"],
            "--early only applies to prepare",
        ),
        ([], "prepare requires --runs-root"),
        (["--early"], "prepare requires --runs-root"),
        (["--step", "install-references"], "install-references requires --grounding"),
    ],
)
def test_cli_rejects_unsafe_mode_combinations(tmp_path, options, message, capsys):
    with pytest.raises(SystemExit):
        driver.parse_args(["--stage-dir", str(tmp_path), *options])
    assert message in capsys.readouterr().err


def test_pin_inputs_needs_the_runs_root(capsys):
    with pytest.raises(SystemExit):
        driver.parse_args(["--step", "pin-inputs"])
    assert "pin-inputs requires --runs-root" in capsys.readouterr().err


def test_partial_mode_is_explicitly_early(tmp_path):
    args = driver.parse_args(
        [
            "--stage-dir",
            str(tmp_path / "stage"),
            "--runs-root",
            str(tmp_path / "runs"),
            "--early",
            "--partial",
        ]
    )
    assert args.partial and args.early and args.step == "prepare"


@pytest.mark.parametrize("step", [*EARLY_STEPS, "install-references"])
def test_every_stage_step_needs_a_stage(step, capsys):
    with pytest.raises(SystemExit):
        driver.parse_args(["--step", step, "--grounding", "g.csv"])
    assert f"{step} requires --stage-dir" in capsys.readouterr().err


def _fail_steps(monkeypatch, keep=()):
    for name in {
        "stage_upgrade",
        "triage",
        "export",
        "judge",
        "bind_seed",
        "install_exclusions",
        "adjudicate_exclusions",
        "write_judge_provenance",
        "resolve_live_base",
    } - set(keep):
        monkeypatch.setattr(driver, name, lambda *a, n=name: pytest.fail(f"{n} ran"))


@pytest.mark.parametrize("step", RESUMED_STEPS)
@pytest.mark.parametrize("change", ["edited", "removed"])
def test_resume_refuses_changed_staged_inputs(workspace, monkeypatch, step, change):
    _fail_steps(monkeypatch)
    stage = workspace / "results/local/stage"
    stage.mkdir(parents=True)
    if change == "edited":
        (stage / "predictions.csv").write_text("changed data")
    (stage / "stage.json").write_text(
        json.dumps(
            {
                "partial": False,
                "early": False,
                "files": {
                    "predictions.csv": hashlib.sha256(b"original data").hexdigest()
                },
            }
        )
    )
    # A removed input stops the step when its digest is read.
    refusal = SystemExit if change == "edited" else FileNotFoundError
    with pytest.raises(refusal, match="staged input changed|predictions.csv"):
        driver.main(["--stage-dir", str(stage), "--step", step])


# Steps that read the installed build and the release's exclusion record.
GATED_STEPS = {
    "triage": "triage",
    "export": "triage",
    "judge": "judge",
    "provenance": "write_judge_provenance",
    "adjudicate-exclusions": "adjudicate_exclusions",
}


def _resumable(stage: Path, **receipt) -> None:
    stage.mkdir(parents=True)
    driver.write_json(
        stage / "stage.json", {"partial": False, "early": False, "files": {}, **receipt}
    )


@pytest.mark.parametrize("step", GATED_STEPS)
@pytest.mark.parametrize("installed", [None, {}, False])
def test_later_steps_refuse_a_stage_without_the_installed_build(
    workspace, monkeypatch, step, installed
):
    _fail_steps(monkeypatch, keep={"stage_upgrade"})
    stage = workspace / "results/local/stage"
    receipt = {} if installed is None else {"references_installed": installed}
    _resumable(stage, **receipt)
    with pytest.raises(SystemExit, match="run --step install-references"):
        driver.main(["--stage-dir", str(stage), "--step", step])


@pytest.mark.parametrize("step", GATED_STEPS)
@pytest.mark.parametrize("installed", [None, {}, {"sha256": "0" * 64}])
def test_later_steps_refuse_a_stage_without_the_build_exclusions(
    workspace, monkeypatch, step, installed
):
    _fail_steps(monkeypatch)
    build = SimpleNamespace(sha256={EXCLUSIONS_NAME: "1" * 64})
    monkeypatch.setattr(driver, "stage_upgrade", lambda stage: build)
    stage = workspace / "results/local/stage"
    receipt = {} if installed is None else {"exclusions_installed": installed}
    _resumable(stage, **receipt)
    with pytest.raises(SystemExit, match="exclusions are not the release's"):
        driver.main(["--stage-dir", str(stage), "--step", step])


@pytest.mark.parametrize("step, called", [*GATED_STEPS.items()])
def test_a_stage_with_the_build_exclusions_reaches_its_step(
    workspace, monkeypatch, step, called
):
    calls = []
    for name in set(GATED_STEPS.values()) | {"export", "resolve_live_base"}:
        monkeypatch.setattr(driver, name, lambda *a, n=name: calls.append(n))
    build = SimpleNamespace(sha256={EXCLUSIONS_NAME: "1" * 64})
    monkeypatch.setattr(driver, "stage_upgrade", lambda stage: build)
    stage = workspace / "results/local/stage"
    _resumable(stage, exclusions_installed={"sha256": "1" * 64})
    driver.main(["--stage-dir", str(stage), "--step", step])
    expected = [called] if step != "export" else ["triage", "resolve_live_base"]
    assert calls[: len(expected)] == expected


@pytest.mark.parametrize(
    "step, called",
    [("install-exclusions", "install_exclusions"), ("bind-seed", "bind_seed")],
)
def test_the_steps_before_installation_do_not_need_the_build(
    workspace, monkeypatch, step, called
):
    _fail_steps(monkeypatch)
    calls = []
    monkeypatch.setattr(driver, called, lambda *a: calls.append(called))
    stage = workspace / "results/local/stage"
    _resumable(stage)
    driver.main(["--stage-dir", str(stage), "--step", step])
    assert calls == [called]


# --- Seed binding and prompt partitions (ported from test_finish_argon.py) -------

# A three-household board whose audit prompts render for real (policybench.audit).
REFERENCE_ROWS = [
    {"scenario_id": "s0", "variable": "snap", "value": 0.0},
    {"scenario_id": "s1", "variable": "snap", "value": 300.0},
    {"scenario_id": "s2", "variable": "snap", "value": 100.0},
]
INCUMBENT_ROWS = [
    ("m1", "s0", 250.0, "Estimated benefit from income."),
    ("m2", "s0", 400.0, "Used gross income test."),
    ("m1", "s1", 300.0, "Matched the allotment."),
    ("m2", "s1", 0.0, "Assumed ineligible."),
    ("m1", "s2", 100.0, "Matched the allotment."),
    ("m2", "s2", 100.0, "Matched the allotment."),
]
# GPT-6.1 Terra misses s0 alone: s0 is re-opened, s1 carries over.
JOINS_S0 = [
    (NEW, "s0", 99.0, "Guessed."),
    (NEW, "s1", 300.0, "Right."),
    (NEW, "s2", 100.0, "Right."),
]
# GPT-6.1 Terra answers every output right: no case is joined.
JOINS_NONE = [
    (NEW, "s0", 0.0, "Ineligible."),
    (NEW, "s1", 300.0, "Right."),
    (NEW, "s2", 100.0, "Right."),
]
COMMITTED_SEED_DIGEST_SHA256 = driver.SEED_DIGEST_SHA256


def _board(directory: Path, rows, references=REFERENCE_ROWS) -> Path:
    us = directory / "us"
    us.mkdir(parents=True)
    pd.DataFrame(references).to_csv(us / CSV_NAME, index=False)
    pd.DataFrame(
        [
            {
                "model": model,
                "scenario_id": scenario,
                "variable": "snap",
                "prediction": value,
                "explanation": text,
                "error": None,
            }
            for model, scenario, value, text in rows
        ]
    ).to_csv(us / "predictions.csv", index=False)
    return directory


def _audit(root: Path, wrong_models) -> Path:
    from policybench.judge_template import template_header

    case = root / "cases/us__scenario_000__snap"
    case.mkdir(parents=True)
    (case / "prompt.md").write_text(template_header(2) + "\nClassify these.\n")
    driver.write_json(root / "schema.json", AUDIT_OUTPUT_SCHEMA)
    (root / "cases.jsonl").write_text(
        json.dumps(
            {
                "case_id": case.name,
                "wrong_models": wrong_models,
                "parse_failure_only": False,
            }
        )
        + "\n"
    )
    return case


@pytest.fixture
def seeded_stage(tmp_path, monkeypatch):
    """A judged two-incumbent seed audit and a stage whose board adds Terra.

    MOCK: a synthetic seed judged on template v1 by another judge, its
    sidecars recording no prompt or template version, as release 20261014's
    oldest carried verdicts do. No reference build is installed, so only the
    cases Terra joins may re-open.
    """
    from policybench.audit import prepare_audit

    monkeypatch.setattr(driver, "reworded_since_seed", lambda: frozenset())
    grounding = tmp_path / "grounding.csv"
    pd.DataFrame(
        [{"scenario_id": "s1", "variable": "snap", "grounding": "Gross test: pass."}]
    ).to_csv(grounding, index=False)
    monkeypatch.setattr(driver, "GROUNDING_SHA256", sha(grounding))
    lookup = {("s1", "snap"): "Gross test: pass."}
    seed = tmp_path / "seed"
    seed_board = _board(tmp_path / "seed-board", INCUMBENT_ROWS)
    prepare_audit(seed_board / "us", seed, grounding_lookup=lookup, template_version=1)
    for item in map(json.loads, (seed / "cases.jsonl").read_text().splitlines()):
        write_verdict(
            seed / "cases" / item["case_id"],
            _verdict(item["wrong_models"]),
            judge_model_requested="default",
            judge_model_reported=["gpt-6.1-sol"],
            judge_runner="scripts/run_audit_codex.sh",
            prompt_sha256=None,
            judge_template_version=None,
        )
    digest_text = driver.seed_digest_text(driver.seed_digest(seed))
    monkeypatch.setattr(driver, "SEED_DIGEST_SHA256", sha(digest_text.encode()))
    stage = tmp_path / "stage"

    def prepare(
        new_rows, *, grounding_path=grounding, explanations=None, references=None
    ):
        bundle = _board(
            stage / "publish" / driver.RUN_NAME,
            INCUMBENT_ROWS + new_rows,
            references or REFERENCE_ROWS,
        )
        if explanations:
            (bundle / "annotations").mkdir()
            pd.DataFrame(
                [
                    {"scenario_id": scenario, "variable": "snap", "explanation": text}
                    for scenario, text in explanations.items()
                ]
            ).to_csv(bundle / "annotations" / driver.EXPLANATIONS_NAME, index=False)
        args = SimpleNamespace(
            stage_dir=stage, audit_seed=seed, grounding=grounding_path
        )
        binding = driver.prepare_cases(args, bundle)
        # main binds the seed in stage.json beside the input hashes.
        driver.write_json(
            stage / "stage.json",
            {"partial": False, "early": False, "files": {}, "seed": binding},
        )
        return stage / "audit"

    return seed, stage, prepare


def test_a_case_terra_joins_is_rejudged_and_the_rest_carry_over(seeded_stage):
    seed, stage, prepare = seeded_stage
    audit = prepare(JOINS_S0)
    joined, untouched = "us__s0__snap", "us__s1__snap"
    assert json.loads((stage / "pending.json").read_text()) == [joined]
    assert not (audit / "cases" / joined / "verdict.json").exists()
    assert not (audit / "cases" / joined / "verdict.meta.json").exists()
    for name in ("prompt.md", "verdict.json", "verdict.meta.json"):
        assert (audit / "cases" / untouched / name).read_bytes() == (
            seed / "cases" / untouched / name
        ).read_bytes()
    assert json.loads((stage / driver.PROMPT_CHANGES).read_text()) == {
        "added": [],
        "changed": [joined],
        "kept": [untouched],
    }
    write_verdict(audit / "cases" / joined, _verdict(["m1", "m2", NEW]))
    binding = driver.load_seed(stage)
    assert binding == driver.seed_digest(seed)
    assert driver.rejudged_cases(stage) == {joined}
    assert driver.validate_verdicts(audit, seed=binding) == []


def test_a_rejudged_case_by_the_seeds_judge_stays_pending(seeded_stage):
    """The joined case's new verdict must come from this release's judge; the
    seed's own judge and runner do not qualify."""
    _, stage, prepare = seeded_stage
    audit = prepare(JOINS_S0)
    write_verdict(
        audit / "cases/us__s0__snap",
        _verdict(["m1", "m2", NEW]),
        judge_model_requested="default",
        judge_model_reported=["gpt-6.1-sol"],
        judge_runner="scripts/run_audit_codex.sh",
    )
    assert driver.validate_verdicts(audit, seed=driver.load_seed(stage)) == [
        "us__s0__snap"
    ]


@pytest.mark.parametrize("mutation", ["edited", "rebound", "missing"])
def test_an_edited_carried_over_verdict_is_refused_after_prepare(
    seeded_stage, mutation
):
    """Edit a kept incumbent verdict in a prepared stage (sidecar re-hashed to
    match, or by this release's judge), or remove it, and validation refuses
    it without setting anything aside."""
    _, stage, prepare = seeded_stage
    audit = prepare(JOINS_S0)
    write_verdict(audit / "cases/us__s0__snap", _verdict(["m1", "m2", NEW]))
    seed = driver.load_seed(stage)
    assert driver.validate_verdicts(audit, seed=seed) == []
    kept = audit / "cases/us__s1__snap"
    verdict = json.loads((kept / "verdict.json").read_text())
    verdict["case_failure_source"] = "prompt_ambiguity"
    if mutation == "edited":
        (kept / "verdict.json").write_text(json.dumps(verdict))
    elif mutation == "rebound":
        write_verdict(kept, verdict)
    else:
        (kept / "verdict.json").unlink()
    before = sorted(p.name for p in kept.iterdir())
    with pytest.raises(SystemExit, match="carried-over verdicts differ.*us__s1__snap"):
        driver.validate_verdicts(audit, remove_invalid=True, seed=seed)
    assert sorted(p.name for p in kept.iterdir()) == before


def test_prepare_refuses_a_seed_the_committed_digest_does_not_record(
    seeded_stage, monkeypatch
):
    _, stage, prepare = seeded_stage
    monkeypatch.setattr(driver, "SEED_DIGEST_SHA256", COMMITTED_SEED_DIGEST_SHA256)
    with pytest.raises(SystemExit, match="not release 20261014's"):
        prepare(JOINS_S0)
    assert not (stage / "audit").exists()


@pytest.mark.parametrize("field", ["prompt_sha256", "verdict_sha256"])
def test_load_seed_refuses_a_stage_without_a_binding_or_with_another(
    seeded_stage, field
):
    _, stage, prepare = seeded_stage
    prepare(JOINS_S0)
    receipt = json.loads((stage / "stage.json").read_text())
    edited = copy.deepcopy(receipt)
    edited["seed"]["us__s1__snap"][field] = "0" * 64
    driver.write_json(stage / "stage.json", edited)
    with pytest.raises(SystemExit, match="not release 20261014's"):
        driver.load_seed(stage)
    added = copy.deepcopy(receipt)
    added["seed"]["us__s9__snap"] = added["seed"]["us__s1__snap"]
    driver.write_json(stage / "stage.json", added)
    with pytest.raises(SystemExit, match="not release 20261014's"):
        driver.load_seed(stage)
    del receipt["seed"]
    driver.write_json(stage / "stage.json", receipt)
    with pytest.raises(SystemExit, match="bind-seed --audit-seed <the 20261014"):
        driver.load_seed(stage)


def test_bind_seed_binds_a_stage_prepared_before_prepare_did(seeded_stage):
    seed, stage, prepare = seeded_stage
    prepare(JOINS_S0)
    receipt = json.loads((stage / "stage.json").read_text())
    binding = receipt.pop("seed")
    driver.write_json(stage / "stage.json", receipt)
    args = SimpleNamespace(stage_dir=stage, audit_seed=seed)
    driver.bind_seed(args)
    assert driver.load_seed(stage) == binding
    with pytest.raises(SystemExit, match="already binds"):
        driver.bind_seed(args)


def test_bind_seed_before_prepare_binds_the_install_record_once(tmp_path, seeded_stage):
    """Before prepare, bind-seed writes the seed into reference-install.json,
    refuses a seed the committed digest does not record and binds only once."""
    seed, _, _ = seeded_stage
    stage = tmp_path / "early-stage"
    stage.mkdir()
    args = SimpleNamespace(stage_dir=stage, audit_seed=seed)
    with pytest.raises(SystemExit, match="installed build or prepared stage"):
        driver.bind_seed(args)
    driver.write_json(stage / "reference-install.json", {"sha256": {}})
    driver.bind_seed(args)
    marker = json.loads((stage / "reference-install.json").read_text())
    assert marker["seed"] == driver.seed_digest(seed)
    with pytest.raises(SystemExit, match="already binds its audit seed"):
        driver.bind_seed(args)


def test_bind_seed_before_prepare_refuses_another_seed(
    tmp_path, seeded_stage, monkeypatch
):
    seed, _, _ = seeded_stage
    stage = tmp_path / "early-stage"
    stage.mkdir()
    driver.write_json(stage / "reference-install.json", {"sha256": {}})
    monkeypatch.setattr(driver, "SEED_DIGEST_SHA256", COMMITTED_SEED_DIGEST_SHA256)
    with pytest.raises(SystemExit, match="not release 20261014's"):
        driver.bind_seed(SimpleNamespace(stage_dir=stage, audit_seed=seed))
    assert "seed" not in json.loads((stage / "reference-install.json").read_text())


@pytest.mark.parametrize(
    "move", ["kept_to_changed", "changed_to_kept", "dropped", "kept_to_added"]
)
def test_prompt_changes_that_disagree_with_the_stage_stop_every_step(
    seeded_stage, move
):
    """prompt-changes.json is re-derived from the stage's prompts and the
    bound seed on every read: moving a case between the lists, or dropping
    one, is refused."""
    _, stage, prepare = seeded_stage
    prepare(JOINS_S0)
    path = stage / driver.PROMPT_CHANGES
    changes = json.loads(path.read_text())
    if move == "kept_to_changed":
        changes["kept"].remove("us__s1__snap")
        changes["changed"].append("us__s1__snap")
    elif move == "changed_to_kept":
        changes["changed"].remove("us__s0__snap")
        changes["kept"].append("us__s0__snap")
    elif move == "kept_to_added":
        changes["kept"].remove("us__s1__snap")
        changes["added"].append("us__s1__snap")
    else:
        changes["changed"].remove("us__s0__snap")
    path.write_text(json.dumps(changes))
    for step in (driver.load_seed, driver.rejudged_cases):
        with pytest.raises(SystemExit, match="disagrees with the stage's prompts"):
            step(stage)


@pytest.mark.parametrize("edit", ["prompt_only", "verdict_sidecar_and_prompt"])
def test_a_kept_case_cannot_pass_as_a_new_verdict(seeded_stage, edit):
    """A kept case whose prompt is edited (with or without a re-bound
    verdict by this release's judge) is refused, never re-judged."""
    _, stage, prepare = seeded_stage
    audit = prepare(JOINS_S0)
    write_verdict(audit / "cases/us__s0__snap", _verdict(["m1", "m2", NEW]))
    kept = audit / "cases/us__s1__snap"
    (kept / "prompt.md").write_text((kept / "prompt.md").read_text() + "\n")
    if edit == "verdict_sidecar_and_prompt":
        verdict = json.loads((kept / "verdict.json").read_text())
        verdict["case_failure_subtype"] = "other"
        write_verdict(kept, verdict)
    before = sorted(p.name for p in kept.iterdir())
    with pytest.raises(SystemExit, match="incumbent-only case prompts changed"):
        driver.load_seed(stage)
    assert sorted(p.name for p in kept.iterdir()) == before


@pytest.mark.parametrize("claim", ["reopens_a_right_answer", "keeps_a_wrong_answer"])
def test_the_manifest_cannot_reopen_a_case_the_predictions_do_not(seeded_stage, claim):
    """Terra answers s1 right and s0 wrong. Listing it as wrong on s1 (prompt
    edited, case moved to changed), or dropping it from s0 (seed prompt
    restored, case moved to kept), leaves the re-derived lists agreeing, so
    only the predictions can refuse the forged manifest."""
    seed, stage, prepare = seeded_stage
    audit = prepare(JOINS_S0)
    driver.load_seed(stage)
    manifest = [
        json.loads(line) for line in (audit / "cases.jsonl").read_text().splitlines()
    ]
    changes = json.loads((stage / driver.PROMPT_CHANGES).read_text())
    case = "us__s1__snap" if claim == "reopens_a_right_answer" else "us__s0__snap"
    row = next(item for item in manifest if item["case_id"] == case)
    if claim == "reopens_a_right_answer":
        row["wrong_models"].append(NEW)
        prompt = audit / "cases" / case / "prompt.md"
        prompt.write_text(prompt.read_text() + f"{NEW}: Wrong.\n")
        changes["kept"].remove(case)
        changes["changed"].append(case)
    else:
        row["wrong_models"].remove(NEW)
        shutil.copyfile(
            seed / "cases" / case / "prompt.md", audit / "cases" / case / "prompt.md"
        )
        changes["changed"].remove(case)
        changes["kept"].append(case)
    (audit / "cases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in manifest))
    (stage / driver.PROMPT_CHANGES).write_text(json.dumps(changes))
    for step in (driver.load_seed, driver.rejudged_cases):
        with pytest.raises(
            SystemExit, match=f"disagree with the staged predictions.*{case}"
        ):
            step(stage)


@pytest.mark.parametrize("defect", ["kept_verdict", "kept_prompt", "changed_prompt"])
def test_bind_seed_refuses_a_stage_that_disagrees_with_the_seed(seeded_stage, defect):
    seed, stage, prepare = seeded_stage
    audit = prepare(JOINS_S0)
    receipt = json.loads((stage / "stage.json").read_text())
    del receipt["seed"]
    driver.write_json(stage / "stage.json", receipt)
    if defect == "kept_verdict":
        (audit / "cases/us__s1__snap/verdict.json").write_text("{}")
    elif defect == "kept_prompt":
        (audit / "cases/us__s1__snap/prompt.md").write_text("Another prompt.\n")
    else:
        shutil.copyfile(
            seed / "cases/us__s0__snap/prompt.md",
            audit / "cases/us__s0__snap/prompt.md",
        )
    with pytest.raises(SystemExit, match="disagrees with the seed"):
        driver.bind_seed(SimpleNamespace(stage_dir=stage, audit_seed=seed))
    assert "seed" not in json.loads((stage / "stage.json").read_text())


def test_a_household_only_terra_misses_becomes_a_new_case(seeded_stage):
    _, stage, prepare = seeded_stage
    audit = prepare(
        [
            (NEW, "s0", 0.0, "Ineligible."),
            (NEW, "s1", 300.0, "Right."),
            (NEW, "s2", 55.0, "Halved."),
        ]
    )
    assert json.loads((stage / driver.PROMPT_CHANGES).read_text()) == {
        "added": ["us__s2__snap"],
        "changed": [],
        "kept": ["us__s0__snap", "us__s1__snap"],
    }
    assert json.loads((stage / "pending.json").read_text()) == ["us__s2__snap"]
    assert not (audit / "cases/us__s2__snap/verdict.json").exists()


def test_an_incumbent_prompt_that_changes_is_refused(
    seeded_stage, tmp_path, monkeypatch
):
    _, _, prepare = seeded_stage
    other = tmp_path / "other-grounding.csv"
    pd.DataFrame(
        [{"scenario_id": "s1", "variable": "snap", "grounding": "Gross test: fail."}]
    ).to_csv(other, index=False)
    monkeypatch.setattr(driver, "GROUNDING_SHA256", sha(other))
    with pytest.raises(SystemExit, match=r"incumbent-only case prompts changed.*s1"):
        prepare(JOINS_S0, grounding_path=other)


def test_a_moved_reference_without_the_installed_build_is_refused(seeded_stage):
    """A reference value that moves outside an installed build's record
    re-renders an incumbent-only prompt, which prepare refuses."""
    _, _, prepare = seeded_stage
    moved = [
        {**row, "value": 310.0} if row["scenario_id"] == "s1" else row
        for row in REFERENCE_ROWS
    ]
    rows = [(NEW, "s0", 99.0, "Guessed."), (NEW, "s1", 310.0, "Right.")]
    with pytest.raises(SystemExit, match=r"incumbent-only case prompts changed.*s1"):
        prepare([*rows, (NEW, "s2", 100.0, "Right.")], references=moved)


def test_a_reworded_explanation_outside_the_pinned_set_is_refused(seeded_stage):
    _, _, prepare = seeded_stage
    with pytest.raises(
        SystemExit, match=r"incumbent-only case prompts changed.*\['us__s1__snap'\]"
    ):
        prepare(JOINS_S0, explanations={"s1": "The allotment is the maximum."})


def test_prepare_refuses_a_grounding_other_than_the_pinned_one(seeded_stage, tmp_path):
    _, stage, prepare = seeded_stage
    other = tmp_path / "other-grounding.csv"
    other.write_text("scenario_id,variable,grounding\n")
    with pytest.raises(SystemExit, match="grounding differs"):
        prepare([], grounding_path=other)
    assert not (stage / "audit").exists()


def test_set_aside_keeps_the_judge_evidence_with_the_verdict(tmp_path):
    root = tmp_path / "audit"
    case = _audit(root, [NEW])
    write_verdict(case, _verdict(["someone-else"]))
    for name in ("claude.json", "claude.log", "claude.transcript.jsonl"):
        (case / name).write_text(name)
    assert driver.validate_verdicts(root, remove_invalid=True) == [case.name]
    (kept,) = (tmp_path / "rejected-verdicts" / case.name).iterdir()
    assert sorted(p.name for p in kept.iterdir()) == [
        "claude.json",
        "claude.log",
        "claude.transcript.jsonl",
        "reason.txt",
        "verdict.json",
        "verdict.meta.json",
    ]
    assert sorted(p.name for p in case.iterdir()) == ["prompt.md"]


@pytest.mark.parametrize("payload", [[], "text", {"amendments": {}}])
def test_a_malformed_amendment_file_is_refused(tmp_path, payload):
    (tmp_path / driver.AMENDMENTS).write_text(json.dumps(payload))
    with pytest.raises(SystemExit, match="'amendments' is not a list"):
        driver.load_amendments(tmp_path, frozenset())


def test_check_prompt_changes_names_new_incumbent_only_cases(tmp_path, monkeypatch):
    monkeypatch.setattr(driver, "reworded_since_seed", lambda: frozenset())
    root = tmp_path / "audit"
    case = _audit(root, ["incumbent"])
    with pytest.raises(SystemExit, match=case.name):
        driver.check_prompt_changes(root, {})
    manifest = json.loads((root / "cases.jsonl").read_text())
    manifest["wrong_models"] = ["incumbent", NEW]
    (root / "cases.jsonl").write_text(json.dumps(manifest) + "\n")
    assert driver.check_prompt_changes(root, {})["added"] == [case.name]
    with pytest.raises(SystemExit, match="seed cases vanished.*us__s9__snap"):
        driver.check_prompt_changes(root, {"us__s9__snap": "0" * 64})
