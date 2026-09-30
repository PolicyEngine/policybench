"""The GPT-6.1 Sol addition cannot move an incumbent or a reference.

Adapted from test_finish_adds0928.py. Synthetic data stands in for runs,
audits and payloads; the committed snapshot is read only where a test pins it.
"""

from __future__ import annotations

import contextlib
import copy
import gzip
import hashlib
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import finish_gpt61sol as driver  # noqa: E402

from policybench.audit import AUDIT_OUTPUT_SCHEMA  # noqa: E402

NEW = "gpt-6.1-sol"
SLUG = "gpt61sol"
# Release 20260929's audit (the seed) and the grounding it was rendered with.
SEED = Path(
    "/Users/maxghenis/PolicyEngine/policybench-wt/adds0928-stage2/results/local/"
    "adds0928-v3/audit"
)
GROUNDING = Path(
    "/Users/maxghenis/PolicyEngine/policybench/results/local/unified_audit/"
    "grounding.csv"
)


def test_the_addition_is_gpt61sol_alone_on_a_46_model_board():
    assert driver.MODELS == {SLUG: NEW}
    assert driver.BASE_MODELS == 45 and driver.BOARD_MODELS == 46
    assert driver.BASE_OUTPUTS == 1984
    assert driver.BASE_EXCLUSIONS == 56 and driver.BASE_SCORED == 1928
    assert driver.BASE_TAG == "dashboard-data-20260929"
    assert driver.BASE_COMMIT == "d616e67c33b6f80dabf5cb7329f069f9a1de069d"
    assert set(driver.BASE_REFERENCE_SHA256) == set(driver.REFERENCE_FILES)
    assert not hasattr(driver, "reference_revision")
    assert not hasattr(driver, "replay_base_references")


# --- Run discovery -------------------------------------------------------------


@pytest.fixture
def runs(tmp_path):
    root = tmp_path / "runs"
    directory = root / SLUG / "run"
    directory.mkdir(parents=True)
    (directory / "run_state.json").write_text(
        json.dumps(
            {"model": NEW, "completed": 100, "total": 100, "stopped_reason": None}
        )
    )
    (directory / "predictions.csv").write_text("model,scenario_id,variable\n")
    return root


def change_state(root, **changes):
    path = root / SLUG / "run/run_state.json"
    state = json.loads(path.read_text())
    state.update(changes)
    path.write_text(json.dumps(state))


def test_discovers_only_the_registered_model(runs):
    extra = runs / "gpt6sol/run"
    extra.mkdir(parents=True)
    (extra / "run_state.json").write_text(json.dumps({"model": "gpt-6-sol"}))
    found = driver.discover_new_models(runs)
    assert [(run.slug, run.model) for run in found] == [(SLUG, NEW)]
    assert found[0].predictions.parent == found[0].run_dir


@pytest.mark.parametrize(
    "changes",
    [
        {"completed": 99},
        {"completed": 38},
        {"stopped_reason": "budget exhausted"},
        {"stopped_reason": ""},
        {"stopped_reason": False},
        {"completed": 0, "total": 0},
        {"completed": -1, "total": -1},
        {"completed": True, "total": True},
        {"completed": 100.0, "total": 100.0},
        {"completed": "100", "total": "100"},
    ],
)
def test_an_incomplete_or_stopped_run_is_refused(runs, changes):
    change_state(runs, **changes)
    with pytest.raises(SystemExit, match="refusing incomplete additions"):
        driver.discover_new_models(runs)


@pytest.mark.parametrize("model", ["gpt-6-sol", "gpt-6.1-luna", "", None])
def test_the_wrong_model_in_a_run_state_is_refused(runs, model):
    change_state(runs, model=model)
    with pytest.raises(SystemExit, match="unexpected model"):
        driver.discover_new_models(runs)


@pytest.mark.parametrize("name", ["run_state.json", "predictions.csv"])
def test_a_missing_run_artifact_is_refused(runs, name):
    (runs / SLUG / "run" / name).unlink()
    with pytest.raises(SystemExit, match=SLUG):
        driver.discover_new_models(runs)


def test_scratch_completion_still_requires_completed_equal_total(runs):
    change_state(runs, completed=4, total=5, synthetic_partial=True)
    with pytest.raises(SystemExit, match="4/5"):
        driver.discover_new_models(runs)
    change_state(runs, completed=5)
    assert len(driver.discover_new_models(runs)) == 1


# --- Stage isolation -----------------------------------------------------------


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setattr(driver, "ROOT", root)
    return root


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


def test_stage_cannot_contain_symlink_to_a_live_file(workspace):
    stage = workspace / "results/local/stage"
    stage.mkdir(parents=True)
    (stage / "predictions.csv").symlink_to(workspace / "live.csv")
    with pytest.raises(SystemExit, match="symlink in stage-dir"):
        driver.validate_stage_path(stage, [])


def test_disjoint_scratch_stage_is_allowed(workspace):
    driver.validate_stage_path(
        workspace / "results/local/stage", [workspace / "results/local/inputs"]
    )


# --- Prediction keys -----------------------------------------------------------


@pytest.fixture
def predictions():
    return pd.DataFrame(
        {
            "model": [NEW, NEW],
            "scenario_id": ["scenario_000", "scenario_000"],
            "variable": ["snap", "ssi"],
            "prediction": [0, 1],
        }
    )


def test_equal_row_counts_do_not_hide_substituted_output_keys(predictions):
    wrong = predictions.copy()
    wrong.loc[1, "variable"] = "medicaid"
    with pytest.raises(SystemExit, match="keys differ"):
        driver.validate_keys(wrong, predictions, NEW)


def test_duplicate_output_keys_are_rejected(predictions):
    repeated = pd.concat([predictions, predictions.iloc[:1]], ignore_index=True)
    with pytest.raises(SystemExit, match="duplicate prediction keys"):
        driver.validate_keys(repeated, predictions, NEW)


def test_predictions_cannot_be_labeled_as_another_model(predictions):
    with pytest.raises(SystemExit, match="unexpected model"):
        driver.validate_keys(predictions, predictions, "gpt-6-sol")


# --- CLI -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "options, message",
    [
        (["--partial"], "--partial requires --early"),
        (["--early", "--step", "judge"], "--early only applies to prepare"),
        (["--early", "--step", "triage"], "--early only applies to prepare"),
        (["--early", "--step", "export"], "--early only applies to prepare"),
        ([], "prepare requires --runs-root"),
    ],
)
def test_cli_rejects_unsafe_mode_combinations(tmp_path, options, message, capsys):
    with pytest.raises(SystemExit):
        driver.parse_args(["--stage-dir", str(tmp_path), *options])
    assert message in capsys.readouterr().err


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


@pytest.mark.parametrize("field", ["partial", "early"])
def test_an_early_or_partial_stage_cannot_resume_into_release(workspace, field):
    stage = workspace / "results/local/stage"
    stage.mkdir(parents=True)
    receipt = {"partial": False, "early": False, "files": {}}
    receipt[field] = True
    (stage / "stage.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="cannot become a release"):
        driver.main(["--stage-dir", str(stage), "--step", "export"])


def test_resume_refuses_changed_staged_inputs(workspace):
    stage = workspace / "results/local/stage"
    stage.mkdir(parents=True)
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
    with pytest.raises(SystemExit, match="staged input changed"):
        driver.main(["--stage-dir", str(stage), "--step", "export"])


# --- Reference pins ------------------------------------------------------------


def test_the_committed_references_match_their_pins():
    driver.verify_reference_pins(driver.SNAPSHOT, "committed reference")
    for name, pin in driver.BASE_REFERENCE_SHA256.items():
        raw = (driver.SNAPSHOT / name).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == pin
    from policybench.reference_exclusions import (
        load_reference_exclusions,
        split_reference,
    )

    exclusions = load_reference_exclusions(driver.SNAPSHOT)
    assert len(exclusions) == driver.BASE_EXCLUSIONS
    reasons = [e["reason_code"] for e in exclusions]
    assert reasons.count("reference_engine_defect") == 28
    assert reasons.count("reference_depends_on_unlisted_input") == 28
    reference = pd.read_csv(driver.SNAPSHOT / "reference_outputs.csv")
    assert len(reference) == driver.BASE_OUTPUTS
    assert reference.scenario_id.nunique() == 100
    assert len(split_reference(reference, exclusions)[0]) == driver.BASE_SCORED


def test_the_committed_adjudications_exclude_exactly_the_scoring_exclusions():
    """Triage requires this of the staged copy, which prepare takes from here."""
    from policybench.adjudications import excluded_case_keys, load_adjudications
    from policybench.reference_exclusions import (
        exclusion_keys,
        load_reference_exclusions,
    )

    decisions = load_adjudications(driver.ANNOTATIONS / "us_adjudications.json")
    assert excluded_case_keys(decisions) == exclusion_keys(
        load_reference_exclusions(driver.SNAPSHOT)
    )
    # Excluded on review of release 20260929, apart from any engine change.
    assert ("scenario_023", "head_medicaid_eligible") in excluded_case_keys(decisions)


@pytest.fixture
def pinned_copy(tmp_path):
    """A copy of the five committed reference files."""
    directory = tmp_path / "references"
    directory.mkdir()
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, directory / name)
    return directory


@pytest.mark.parametrize("name", driver.REFERENCE_FILES)
@pytest.mark.parametrize("defect", ["appended", "missing"])
def test_a_reference_file_that_misses_its_pin_is_refused(pinned_copy, name, defect):
    driver.verify_reference_pins(pinned_copy, "staged reference")
    if defect == "missing":
        (pinned_copy / name).unlink()
    else:
        with (pinned_copy / name).open("a") as stream:
            stream.write("\n")
    with pytest.raises(SystemExit, match=f"staged reference {name} does not match"):
        driver.verify_reference_pins(pinned_copy, "staged reference")


def test_resolve_base_checks_the_committed_pins_before_anything_else(
    pinned_copy, monkeypatch
):
    (pinned_copy / "reference_exclusions.json").write_text('{"exclusions": []}\n')
    monkeypatch.setattr(driver, "SNAPSHOT", pinned_copy)
    monkeypatch.setattr(
        driver,
        "live_pointer",
        lambda: pytest.fail("resolve_base read the pointer before the pins"),
    )
    with pytest.raises(
        SystemExit, match="committed reference reference_exclusions.json"
    ):
        driver.resolve_base(SimpleNamespace(partial=False))


# --- Base payload in git -------------------------------------------------------


def test_the_base_commit_holds_release_20260929():
    pointer = json.loads(driver.base_commit_blob(Path("app/src/data.artifact.json")))
    assert pointer["tag"] == driver.BASE_TAG
    assert pointer["sha256"] == driver.BASE_SHA256
    for name, pin in driver.BASE_REFERENCE_SHA256.items():
        raw = driver.base_commit_blob(driver.SNAPSHOT.relative_to(driver.ROOT) / name)
        assert hashlib.sha256(raw).hexdigest() == pin


def test_base_commit_blob_names_the_missing_history():
    with pytest.raises(SystemExit, match="cannot read .* at base commit d616e67c33b6"):
        driver.base_commit_blob(Path("no/such/file.csv"))


def test_base_commit_blob_names_a_missing_commit(monkeypatch):
    monkeypatch.setattr(driver, "BASE_COMMIT", "0" * 40)
    with pytest.raises(SystemExit, match="at base commit 000000000000.*unshallow"):
        driver.base_commit_blob(Path("app/src/data.artifact.json"))


def test_a_re_export_after_the_freeze_reads_20260929_from_git(monkeypatch):
    """After the freeze the pointer names RELEASE_TAG; the base comes from git."""
    monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": driver.RELEASE_TAG})
    monkeypatch.setattr(
        driver, "resolve_base", lambda args: pytest.fail("read the working tree")
    )
    live = driver.resolve_live_base(SimpleNamespace())
    names = {row["model"] for row in live["countries"]["us"]["modelStats"]}
    assert len(names) == driver.BASE_MODELS and NEW not in names


def _gz_payload(models: int) -> bytes:
    stats = [{"model": f"m{i}"} for i in range(models)]
    return gzip.compress(json.dumps({"modelStats": stats}).encode())


def test_the_git_base_must_rewrap_to_the_20260929_asset(monkeypatch):
    raw = _gz_payload(45)
    monkeypatch.setattr(driver, "base_commit_blob", lambda path: raw)
    monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": driver.RELEASE_TAG})
    with pytest.raises(SystemExit, match="base payload SHA256 mismatch"):
        driver.resolve_live_base(SimpleNamespace())
    wrapped = json.dumps({"countries": {"us": json.loads(gzip.decompress(raw))}})
    monkeypatch.setattr(
        driver, "BASE_SHA256", hashlib.sha256(wrapped.encode()).hexdigest()
    )
    assert (
        len(
            driver.resolve_live_base(SimpleNamespace())["countries"]["us"]["modelStats"]
        )
        == 45
    )
    short = _gz_payload(44)
    monkeypatch.setattr(driver, "base_commit_blob", lambda path: short)
    wrapped = json.dumps({"countries": {"us": json.loads(gzip.decompress(short))}})
    monkeypatch.setattr(
        driver, "BASE_SHA256", hashlib.sha256(wrapped.encode()).hexdigest()
    )
    with pytest.raises(SystemExit, match="base must have 45 models"):
        driver.resolve_live_base(SimpleNamespace())


@pytest.mark.parametrize("tag", ["dashboard-data-20260922c", "dashboard-data-20991231"])
def test_any_other_pointer_is_refused(monkeypatch, tag):
    monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": tag})
    with pytest.raises(SystemExit, match="base pointer changed"):
        driver.resolve_live_base(SimpleNamespace())


# --- Audit ---------------------------------------------------------------------


def _verdict(models, source="llm_error"):
    return {
        "reference_suspect": False,
        "reference_bug_hypothesis": "",
        "case_failure_source": source,
        "case_failure_subtype": "thresholds_rates",
        "rationale": "The models applied an outdated threshold.",
        "models": [
            {
                "model": model,
                "failure_source": source,
                "failure_subtype": "thresholds_rates",
                "diagnosis": "The model used the prior year's threshold.",
            }
            for model in models
        ],
    }


def write_verdict(case, verdict, **meta):
    path = case / "verdict.json"
    path.write_text(json.dumps(verdict))
    (case / "verdict.meta.json").write_text(
        json.dumps(
            {
                "verdict_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "judge_runner": "scripts/run_audit_claude.sh",
                "judge_model_requested": driver.JUDGE_MODEL,
                "judge_model_reported": [driver.JUDGE_MODEL],
                "judged_at_utc": "2026-09-30T01:00:00+00:00",
                **meta,
            }
        )
    )


def _audit(root, wrong_models):
    case = root / "cases/us__scenario_000__snap"
    case.mkdir(parents=True)
    (case / "prompt.md").write_text("Classify these wrong answers.\n")
    (root / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA))
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
def audit(tmp_path):
    root = tmp_path / "audit"
    case = _audit(root, [NEW])
    verdict = _verdict([NEW])
    write_verdict(case, verdict)
    return root, case, verdict


def test_verdict_requires_full_schema_and_exact_wrong_model_coverage(audit):
    root, _, _ = audit
    assert driver.validate_verdicts(root) == []


@pytest.mark.parametrize("defect", ["missing", "extra", "duplicate", "schema", "json"])
def test_invalid_verdict_is_pending_and_removal_clears_provenance(audit, defect):
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
        (case / "verdict.json").write_text("not JSON")
    assert driver.validate_verdicts(root) == [case.name]
    assert (case / "verdict.json").exists()
    assert driver.validate_verdicts(root, remove_invalid=True) == [case.name]
    assert not (case / "verdict.json").exists()
    assert not (case / "verdict.meta.json").exists()


@pytest.mark.parametrize(
    "defect", ["missing", "stale", "wrong_judge", "not_an_object", "no_timestamp"]
)
def test_new_model_verdict_requires_bound_opus55_provenance(audit, defect):
    root, case, _ = audit
    path = case / "verdict.meta.json"
    meta = json.loads(path.read_text())
    if defect == "missing":
        path.unlink()
    else:
        if defect == "stale":
            meta["verdict_sha256"] = "0" * 64
        elif defect == "wrong_judge":
            meta["judge_model_reported"] = ["claude-opus-4-6"]
        elif defect == "no_timestamp":
            del meta["judged_at_utc"]
        else:
            meta = [meta]
        path.write_text(json.dumps(meta))
    assert driver.validate_verdicts(root) == [case.name]


def test_a_verdict_stays_bound_to_its_prompt_sha256(tmp_path):
    root = tmp_path / "audit"
    case = _audit(root, ["incumbent"])
    prompt = hashlib.sha256((case / "prompt.md").read_bytes()).hexdigest()
    write_verdict(
        case,
        _verdict(["incumbent"]),
        prompt_sha256=prompt,
        judge_model_requested="default",
        judge_model_reported=["gpt-5.6-sol"],
    )
    assert driver.validate_verdicts(root) == []
    (case / "prompt.md").write_text("Classify these wrong answers, and one more.\n")
    assert driver.validate_verdicts(root, remove_invalid=True) == [case.name]
    assert not (case / "verdict.json").exists()


def test_the_judge_must_cover_all_46_models_in_a_case(tmp_path):
    incumbents = [f"incumbent-{i:02d}" for i in range(45)]
    root = tmp_path / "audit"
    case = _audit(root, [*incumbents, NEW])
    write_verdict(case, _verdict(incumbents))
    assert driver.validate_verdicts(root) == [case.name]
    write_verdict(case, _verdict([*incumbents, NEW]))
    assert driver.validate_verdicts(root) == []
    # A carried-over incumbent verdict cannot name the new model, and a
    # re-judge from another judge does not qualify.
    write_verdict(
        case,
        _verdict([*incumbents, NEW]),
        judge_model_requested="default",
        judge_model_reported=["gpt-5.6-sol"],
    )
    assert driver.validate_verdicts(root) == [case.name]


def test_parse_only_cases_do_not_require_paid_judging(audit):
    root, case, _ = audit
    manifest = json.loads((root / "cases.jsonl").read_text())
    manifest["parse_failure_only"] = True
    (root / "cases.jsonl").write_text(json.dumps(manifest) + "\n")
    (case / "verdict.json").unlink()
    (case / "verdict.meta.json").unlink()
    assert driver.validate_verdicts(root) == []


def test_unchanged_incumbent_case_keeps_its_existing_judge(tmp_path):
    root = tmp_path / "audit"
    case = _audit(root, ["incumbent"])
    write_verdict(
        case,
        _verdict(["incumbent"]),
        judge_model_requested="default",
        judge_model_reported=["gpt-5.6-sol"],
        judge_runner="scripts/run_audit_codex.sh",
    )
    assert driver.validate_verdicts(root) == []


# A two-household board whose audit prompts render for real (policybench.audit).
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


def _board(directory: Path, rows) -> Path:
    us = directory / "us"
    us.mkdir(parents=True)
    pd.DataFrame(REFERENCE_ROWS).to_csv(us / "reference_outputs.csv", index=False)
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


@pytest.fixture
def seeded_stage(tmp_path, monkeypatch):
    """A judged 2-model seed audit and a stage whose board adds the new model."""
    from policybench.audit import prepare_audit

    grounding = tmp_path / "grounding.csv"
    pd.DataFrame(
        [{"scenario_id": "s1", "variable": "snap", "grounding": "Gross test: pass."}]
    ).to_csv(grounding, index=False)
    monkeypatch.setattr(
        driver, "GROUNDING_SHA256", hashlib.sha256(grounding.read_bytes()).hexdigest()
    )
    lookup = {("s1", "snap"): "Gross test: pass."}
    seed = tmp_path / "seed"
    seed_board = _board(tmp_path / "seed-board", INCUMBENT_ROWS)
    prepare_audit(seed_board / "us", seed, grounding_lookup=lookup)
    for item in map(json.loads, (seed / "cases.jsonl").read_text().splitlines()):
        write_verdict(
            seed / "cases" / item["case_id"],
            _verdict(item["wrong_models"]),
            judge_model_requested="default",
            judge_model_reported=["gpt-5.6-sol"],
        )
    stage = tmp_path / "stage"

    def prepare(new_rows, *, grounding_path=grounding):
        bundle = _board(stage / "publish" / driver.RUN_NAME, INCUMBENT_ROWS + new_rows)
        args = SimpleNamespace(
            stage_dir=stage, audit_seed=seed, grounding=grounding_path
        )
        driver.prepare_cases(args, bundle)
        return stage / "audit"

    return seed, stage, prepare


def test_a_case_the_new_model_joins_is_rejudged_and_the_rest_carry_over(
    seeded_stage,
):
    seed, stage, prepare = seeded_stage
    audit = prepare(
        [
            (NEW, "s0", 99.0, "Guessed."),
            (NEW, "s1", 300.0, "Right."),
            (NEW, "s2", 100.0, "Right."),
        ]
    )
    joined, untouched = "us__s0__snap", "us__s1__snap"
    assert json.loads((stage / "pending.json").read_text()) == [joined]
    assert not (audit / "cases" / joined / "verdict.json").exists()
    assert not (audit / "cases" / joined / "verdict.meta.json").exists()
    for name in ("prompt.md", "verdict.json", "verdict.meta.json"):
        assert (audit / "cases" / untouched / name).read_bytes() == (
            seed / "cases" / untouched / name
        ).read_bytes()
    assert json.loads((stage / "prompt-changes.json").read_text()) == {
        "added": [],
        "changed": [joined],
        "kept": [untouched],
    }
    wrong = ["m1", "m2", NEW]
    write_verdict(audit / "cases" / joined, _verdict(wrong))
    assert driver.validate_verdicts(audit) == []


def test_a_household_only_the_new_model_misses_becomes_a_new_case(seeded_stage):
    _, stage, prepare = seeded_stage
    audit = prepare(
        [
            (NEW, "s0", 0.0, "Ineligible."),
            (NEW, "s1", 300.0, "Right."),
            (NEW, "s2", 55.0, "Halved."),
        ]
    )
    assert json.loads((stage / "prompt-changes.json").read_text()) == {
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
    monkeypatch.setattr(
        driver, "GROUNDING_SHA256", hashlib.sha256(other.read_bytes()).hexdigest()
    )
    rows = [
        (NEW, "s0", 99.0, "Guessed."),
        (NEW, "s1", 300.0, "Right."),
        (NEW, "s2", 100.0, "Right."),
    ]
    with pytest.raises(SystemExit, match=r"incumbent-only case prompts changed.*s1"):
        prepare(rows, grounding_path=other)


def test_prepare_refuses_a_grounding_other_than_the_pinned_one(seeded_stage, tmp_path):
    _, stage, prepare = seeded_stage
    other = tmp_path / "other-grounding.csv"
    other.write_text("scenario_id,variable,grounding\n")
    with pytest.raises(SystemExit, match="grounding differs"):
        prepare([], grounding_path=other)
    assert not (stage / "audit").exists()


def test_the_pinned_grounding_is_the_one_the_20260929_stage_used():
    if not GROUNDING.is_file():
        pytest.skip("the main clone's audit grounding is not on this machine")
    assert driver.digest(GROUNDING) == driver.GROUNDING_SHA256


def test_the_committed_adjudications_keep_the_seed_judge_verdicts():
    """Every recorded decision keeps its seed verdict's class, 023 Medicaid too.

    Triage and the freeze re-check this against the staged audit, where a
    carried-over verdict is the seed's.
    """
    if not SEED.is_dir():
        pytest.skip("release 20260929's audit is not on this machine")
    from freeze_snapshot import verify_adjudications_keep_judge_verdicts

    from policybench.adjudications import load_adjudications

    decisions = load_adjudications(driver.ANNOTATIONS / "us_adjudications.json")
    verify_adjudications_keep_judge_verdicts(decisions, SEED / "cases")
    case = SEED / "cases/us__scenario_023__head_medicaid_eligible"
    meta = json.loads((case / "verdict.meta.json").read_text())
    assert meta["prompt_sha256"] == driver.digest(case / "prompt.md")


@pytest.mark.slow
def test_every_seed_prompt_rerenders_from_the_committed_snapshot(tmp_path):
    """The committed 45-model board renders exactly the seed's cases and prompts.

    So check_prompt_changes may attribute every changed or new prompt in a
    stage to GPT-6.1 Sol joining its case. #182's review excluded
    scenario_023 head_medicaid_eligible and rewrote its adjudication and case
    note; neither enters a prompt, and its prompt is unchanged.
    """
    if not (SEED.is_dir() and GROUNDING.is_file()):
        pytest.skip("release 20260929's audit or grounding is not on this machine")
    from policybench.audit import prepare_audit

    bundle = tmp_path / "publish" / driver.RUN_NAME
    (bundle / "us").mkdir(parents=True)
    for name in (*driver.REFERENCE_FILES, "predictions.csv.gz"):
        shutil.copyfile(driver.SNAPSHOT / name, bundle / "us" / name)
    (bundle / "annotations").mkdir()
    for name in driver.ANNOTATION_FILES:
        shutil.copyfile(driver.ANNOTATIONS / name, bundle / "annotations" / name)
    grounding = pd.read_csv(GROUNDING)
    lookup = {
        (str(r.scenario_id), str(r.variable)): str(r.grounding)
        for r in grounding.itertuples()
    }
    audit = tmp_path / "audit"
    # prepare renders with object strings, as resolve_base sets them.
    arrow = hasattr(pd.options, "future") and hasattr(pd.options.future, "infer_string")
    with (
        pd.option_context("future.infer_string", False)
        if arrow
        else contextlib.nullcontext()
    ):
        prepare_audit(bundle / "us", audit, grounding_lookup=lookup)
    assert (audit / "cases.jsonl").read_bytes() == (SEED / "cases.jsonl").read_bytes()
    rendered = driver.seed_prompt_digests(audit)
    assert rendered == driver.seed_prompt_digests(SEED) and len(rendered) == 674
    case = "us__scenario_023__head_medicaid_eligible"
    meta = json.loads((SEED / "cases" / case / "verdict.meta.json").read_text())
    assert rendered[case] == meta["prompt_sha256"]


def test_check_prompt_changes_names_new_incumbent_only_cases(tmp_path):
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


# --- Triage --------------------------------------------------------------------


@pytest.mark.parametrize(
    "suspect, failure_source, report",
    [
        (True, "llm_error", "reference-flags.csv"),
        (False, "reference_engine_defect", "unresolved-rows.csv"),
        (False, "prompt_ambiguity", "unresolved-rows.csv"),
    ],
)
def test_triage_stops_and_records_flags_for_evidence_review(
    tmp_path, monkeypatch, suspect, failure_source, report
):
    import policybench.audit

    stage = tmp_path / "stage"
    bundle = stage / "publish" / driver.RUN_NAME
    (bundle / "annotations").mkdir(parents=True)
    rows = pd.DataFrame(
        [
            {
                "country": "us",
                "scenario_id": "scenario_000",
                "variable": "snap",
                "model": NEW,
                "failure_source": failure_source,
                "failure_subtype": "thresholds_rates",
                "annotation": "Evidence needed.",
                "reference_suspect": suspect,
            }
        ]
    )
    cases = pd.DataFrame(
        [
            {
                "country": "us",
                "scenario_id": "scenario_000",
                "variable": "snap",
                "wrong_model_count": 1,
                "reference_suspect": suspect,
                "case_failure_source": failure_source,
                "case_failure_subtype": "thresholds_rates",
                "case_annotation": "Evidence needed.",
                "reference_bug_hypothesis": "Check the threshold.",
            }
        ]
    )
    monkeypatch.setattr(driver, "validate_verdicts", lambda *a, **kw: [])
    monkeypatch.setattr(
        policybench.audit,
        "collect_audit",
        lambda *a, **kw: {
            "missing": pd.DataFrame(),
            "hedged": pd.DataFrame(),
            "row": rows,
            "case": cases,
        },
    )
    with pytest.raises(SystemExit, match="triage required"):
        driver.triage(SimpleNamespace(stage_dir=stage), bundle)
    assert len(pd.read_csv(stage / report)) == 1
    assert not (stage / "release-ready.json").exists()


# --- Export and the no-drift gate ---------------------------------------------

FABLE_USAGE = {
    "costUsd": 54.109099999999955,
    "costPerHousehold": 0.5410909999999995,
    "totalTokens": 3850174,
    "latencySeconds": 97.6780539804895,
}


def _stat(model, exact, **usage):
    return {
        "model": model,
        "condition": "no_tools",
        "score": exact / 100,
        "exact": exact,
        "n": 1928,
        **usage,
    }


def _incumbents():
    """45 released rows, including Fable 5's batch usage and Ox Alpha's $0."""
    rows = [_stat(f"incumbent-{i:02d}", 50.0 + i / 7, costUsd=1.25) for i in range(43)]
    rows.append(_stat("ox-alpha", 70.0, costUsd=0.0, costPerHousehold=0.0))
    rows.append(_stat("claude-fable-5", 60.0, costUsd=0.0, costPerHousehold=0.0))
    rows[-1].update(FABLE_USAGE)
    return rows


def _exported(incumbents):
    """What export_full_run returns: Fable's usage is gone, the addition is new."""
    stats = copy.deepcopy(incumbents)
    fable = stats[-1]
    fable.update(costUsd=0.0, costPerHousehold=0.0)
    del fable["totalTokens"], fable["latencySeconds"]
    return stats + [_stat(NEW, 65.0, costUsd=2.0)]


@pytest.fixture
def exporting(tmp_path, monkeypatch):
    import policybench.dashboard_schema
    import policybench.full_run_export

    stage = tmp_path / "stage"
    bundle = stage / "publish" / driver.RUN_NAME
    for name in driver.REFERENCE_FILES:
        (bundle / "us").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(driver.SNAPSHOT / name, bundle / "us" / name)
    exported = {}
    gate_calls = []

    def validate(payload, *, require_failure_annotations):
        gate_calls.append(require_failure_annotations)
        return []

    monkeypatch.setattr(
        policybench.full_run_export,
        "export_full_run",
        lambda *a, **kw: {"countries": {"us": {"modelStats": exported["stats"]}}},
    )
    monkeypatch.setattr(
        policybench.dashboard_schema, "validate_dashboard_payload", validate
    )

    def run(stats, live_stats, *, partial=False, early=False):
        exported["stats"] = stats
        args = SimpleNamespace(stage_dir=stage, partial=partial, early=early)
        live = {"countries": {"us": {"modelStats": live_stats}}}
        return driver.export(args, bundle, live)

    return stage, bundle, run, gate_calls


def _evidence(stage, bundle):
    paths = [
        bundle / "us/predictions.csv",
        bundle / "annotations/us_adjudications.json",
    ]
    paths += [stage / f"inputs/{SLUG}/run_state.json", stage / "audit/cases.jsonl"]
    paths += [stage / "audit/schema.json"]
    paths += [
        stage / "audit/cases/example" / name
        for name in ("verdict.json", "verdict.meta.json", "prompt.md")
    ]
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"Evidence: {path.name}\n")
    return paths + [bundle / "us" / name for name in driver.REFERENCE_FILES]


def test_strict_export_carries_fable_usage_and_binds_the_evidence(exporting):
    stage, bundle, run, gate_calls = exporting
    evidence = _evidence(stage, bundle)
    incumbents = _incumbents()
    stats = _exported(incumbents)
    payload = run(stats, incumbents)

    output = stage / "data-board46.json"
    assert (
        output.read_bytes()
        == json.dumps({"countries": {"us": payload["countries"]["us"]}}).encode()
    )
    assert (bundle / "data.json").read_bytes() == output.read_bytes()
    fable = next(s for s in stats if s["model"] == "claude-fable-5")
    assert json.dumps(fable) == json.dumps(incumbents[-1])
    assert gate_calls == [True]
    receipt = json.loads((stage / "release-ready.json").read_text())
    assert receipt["release_tag"] == driver.RELEASE_TAG
    assert receipt["models"] == 46 and receipt["partial"] is False
    assert receipt["base_sha256"] == driver.BASE_SHA256
    assert receipt["payload_sha256"] == hashlib.sha256(output.read_bytes()).hexdigest()
    assert receipt["files"] == {
        str(path.relative_to(stage)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in evidence
    }


def test_partial_export_never_gets_a_release_receipt(exporting):
    stage, bundle, run, _ = exporting
    stats = [_stat(f"incumbent-{i:02d}", 40.0) for i in range(45)]
    run(stats + [_stat(NEW, 45.0)], [], partial=True, early=True)
    payload = stage / "PARTIAL-data-board46.json"
    assert "PARTIAL" in json.loads(payload.read_text())["stage2Status"]
    assert (bundle / "data.json").read_bytes() == payload.read_bytes()
    assert not (stage / "release-ready.json").exists()


MUTATIONS = {
    "value": lambda row: row.update(exact=row["exact"] + 1e-12),
    "added_key": lambda row: row.update(extra=None),
    "removed_key": lambda row: row.pop("score"),
    "key_order": lambda row: row.update(model=row.pop("model")),
    "int_to_float": lambda row: row.update(n=float(row["n"])),
    "zero_cost_to_missing": lambda row: row.pop("costUsd"),
    "zero_to_negative_zero": lambda row: row.update(costUsd=-row["costUsd"]),
}


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    target=st.integers(min_value=0, max_value=44),
    mutation=st.sampled_from(sorted(MUTATIONS)),
)
def test_the_no_drift_gate_refuses_any_change_to_any_incumbent(
    exporting, target, mutation
):
    """For every incumbent and every kind of change, export refuses."""
    stage, _, run, _ = exporting
    incumbents = _incumbents()
    stats = _exported(incumbents)
    MUTATIONS[mutation](stats[target])
    (stage / "data-board46.json").unlink(missing_ok=True)
    # Fable's usage values are carried over from the base (the exporter cannot
    # recompute them), so a changed value there is replaced by the released
    # one; a missing key comes back out of order and is still refused.
    if target == 44 and mutation == "zero_to_negative_zero":
        run(stats, incumbents, early=True)
        assert json.dumps(stats[target]) == json.dumps(incumbents[target])
        return
    with pytest.raises(SystemExit, match="incumbent modelStats drift"):
        run(stats, incumbents, early=True)
    assert not (stage / "data-board46.json").exists()


@settings(max_examples=60, deadline=None)
@given(
    rows=st.lists(
        st.fixed_dictionaries(
            {
                "exact": st.floats(allow_nan=False, allow_infinity=False),
                "n": st.integers(min_value=0, max_value=1984),
            }
        ),
        min_size=45,
        max_size=45,
    ),
    target=st.integers(min_value=0, max_value=44),
)
def test_incumbent_drift_is_exactly_the_changed_rows(rows, target):
    """Identical rows pass; a changed, dropped or reordered row is named."""
    previous = {
        f"m{i:02d}": {"model": f"m{i:02d}", **row} for i, row in enumerate(rows)
    }
    stats = [copy.deepcopy(row) for row in previous.values()]
    assert driver.incumbent_drift(stats, previous) == []
    name = f"m{target:02d}"
    reordered = copy.deepcopy(stats)
    reordered[target] = dict(reversed(list(reordered[target].items())))
    assert driver.incumbent_drift(reordered, previous) == [name]
    dropped = [row for row in stats if row["model"] != name]
    assert driver.incumbent_drift(dropped, previous) == [name]


def test_the_export_roster_must_be_the_incumbents_plus_the_addition(exporting):
    _, _, run, _ = exporting
    incumbents = _incumbents()
    stats = _exported(incumbents)
    stats[-1] = _stat("gpt-6-sol-impostor", 65.0)
    with pytest.raises(SystemExit, match="roster"):
        run(stats, incumbents)
    with pytest.raises(SystemExit, match="45 incumbents"):
        run(_exported(incumbents), incumbents[:-1] + [_stat(NEW, 1.0)])


@pytest.mark.parametrize("n", [1927, 1929, 1984])
def test_export_refuses_an_addition_not_scored_on_the_1928_outputs(exporting, n):
    stage, _, run, _ = exporting
    incumbents = _incumbents()
    stats = _exported(incumbents)
    stats[-1]["n"] = n
    with pytest.raises(SystemExit, match=f"not scored on the 1928 outputs.*{NEW}"):
        run(stats, incumbents)
    assert not (stage / "data-board46.json").exists()


def test_export_refuses_a_staged_reference_off_its_pin(exporting):
    _, bundle, run, _ = exporting
    path = bundle / "us/reference_outputs.csv.meta.json"
    path.write_bytes(path.read_bytes() + b"\n")
    incumbents = _incumbents()
    with pytest.raises(SystemExit, match="staged reference reference_outputs.csv.meta"):
        run(_exported(incumbents), incumbents)


def test_export_refuses_a_committed_reference_off_its_pin(
    exporting, pinned_copy, monkeypatch
):
    _, _, run, _ = exporting
    (pinned_copy / "scenarios.csv").write_text("scenario_id\n")
    monkeypatch.setattr(driver, "SNAPSHOT", pinned_copy)
    incumbents = _incumbents()
    with pytest.raises(SystemExit, match="committed reference scenarios.csv"):
        run(_exported(incumbents), incumbents)


# --- The fold ------------------------------------------------------------------

REFERENCE = pd.read_csv(driver.SNAPSHOT / "reference_outputs.csv")[driver.KEY]
TEXT = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00"),
    max_size=12,
)
NUMBERS = st.one_of(
    st.none(),
    st.floats(min_value=-1e7, max_value=1e7, allow_nan=False).map(
        lambda x: round(x, 2)
    ),
    st.integers(min_value=0, max_value=10**6).map(float),
)


def _frame(model: str, rng, pools: dict) -> pd.DataFrame:
    count = len(REFERENCE)
    frame = REFERENCE.copy()
    frame.insert(0, "model", model)
    for column, pool in pools.items():
        frame[column] = [pool[i] for i in rng.integers(0, len(pool), count)]
    frame["provider_resolved_model"] = model
    return frame


@settings(max_examples=12, deadline=None)
@given(
    incumbents=st.integers(min_value=1, max_value=3),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
    numbers=st.lists(NUMBERS, min_size=1, max_size=6),
    words=st.lists(TEXT, min_size=1, max_size=6),
    extra_column=st.booleans(),
)
def test_the_fold_keeps_incumbent_rows_and_adds_1984_rows_for_the_addition(
    tmp_path_factory, incumbents, seed, numbers, words, extra_column
):
    """Any board: incumbent rows survive byte for byte; the addition is exact.

    Prediction columns keep their production types: numeric columns are
    floats, and text columns carry prose (a letter before any digits).
    """
    import freeze_snapshot as freezer
    import numpy as np

    from policybench.fold_board import fold_board

    rng = np.random.default_rng(seed)
    prose = [f"x{word}" for word in words] + [None]
    pools = {
        "prediction": numbers,
        "explanation": prose,
        "raw_response": prose,
        "error": [None, "Timeout, retried", 'said "no"'],
        "prompt_tokens": numbers,
        "completion_tokens": numbers,
    }
    root = tmp_path_factory.mktemp("fold")
    base = pd.concat(
        [_frame(f"incumbent-{i}", rng, pools) for i in range(incumbents)],
        ignore_index=True,
    )
    base_path = root / "base-predictions.csv"
    base.to_csv(base_path, index=False)
    addition = _frame(NEW, rng, pools)
    if extra_column:
        addition["provider_system_fingerprint"] = "fp_1"
        addition = addition.drop(columns=["raw_response"])
    addition_path = root / "fold.csv"
    addition.to_csv(addition_path, index=False)
    scoring = root / "scoring"
    scoring.mkdir()
    for name in driver.REFERENCE_FILES:
        shutil.copyfile(driver.SNAPSHOT / name, scoring / name)

    result = fold_board(
        base_path, [addition_path], scoring, root / "fold", export=False
    )

    assert result["excluded"] == {} and result["models"] == incumbents + 1
    folded_path = root / "fold/us/predictions.csv"
    folded = pd.read_csv(folded_path, low_memory=False)
    new_rows = folded[folded.model == NEW]
    assert len(new_rows) == len(REFERENCE) == 1984
    assert set(new_rows[driver.KEY].itertuples(index=False, name=None)) == set(
        REFERENCE.itertuples(index=False, name=None)
    )
    reread = pd.read_csv(base_path, low_memory=False)
    text = {"dtype": str, "keep_default_na": False}
    base_text = pd.read_csv(base_path, **text)
    folded_text = pd.read_csv(folded_path, **text)[base_text.columns]
    for i in range(incumbents):
        model = f"incumbent-{i}"
        assert freezer._model_prediction_rows_sha256(
            folded, model
        ) == freezer._model_prediction_rows_sha256(reread, model)
        before = base_text[base_text.model == model].reset_index(drop=True)
        after = folded_text[folded_text.model == model].reset_index(drop=True)
        pd.testing.assert_frame_equal(before, after)
    for name in driver.REFERENCE_FILES:
        assert (root / "fold/us" / name).read_bytes() == (
            driver.SNAPSHOT / name
        ).read_bytes()


# --- One tag constant ----------------------------------------------------------


def test_the_release_tag_is_named_in_one_place():
    """RELEASE_TAG is the only spelling of the new tag in the driver's files."""
    root = Path(__file__).resolve().parents[1]
    source = (root / "scripts/finish_gpt61sol.py").read_text().splitlines()
    assert sum(driver.RELEASE_TAG in line for line in source) == 1
    for relative in (
        "scripts/freeze_gpt61sol.py",
        "scripts/snapshot_gpt61sol.py",
        "docs/gpt61sol/design.md",
        "tests/test_freeze_gpt61sol.py",
        "tests/test_finish_gpt61sol.py",
    ):
        assert driver.RELEASE_TAG not in (root / relative).read_text(), relative
