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
import json
import shutil
import subprocess
import sys
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


def _verdict(models):
    return {
        "reference_suspect": False,
        "reference_bug_hypothesis": "",
        "case_failure_source": "llm_error",
        "case_failure_subtype": "thresholds_rates",
        "rationale": "The models applied an outdated threshold.",
        "models": [
            {
                "model": m,
                "failure_source": "llm_error",
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
                "prompt_sha256": sha(case / "prompt.md"),
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
