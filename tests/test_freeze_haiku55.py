"""The Claude Haiku 5.5 freeze builds nothing from an unbound or revised stage.

Adapted from test_freeze_gpt61sol.py, with synthetic stages in tmp_path. Release
20261006's committed references, exclusions, adjudications, manifest and
serving configuration are read from git at the driver's BASE_COMMIT, never
written. No test runs the real freezer: freeze_snapshot.main is replaced in
every test, its destinations point into the test's workspace, and a module
fixture checks that the checkout's tracked snapshot files were not touched.
"""

from __future__ import annotations

import copy
import datetime
import functools
import hashlib
import json
import re
import shutil
import sys
import types
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import finish_haiku55 as driver  # noqa: E402
import freeze_haiku55 as release  # noqa: E402
import freeze_snapshot as freezer  # noqa: E402

from policybench.audit import AUDIT_OUTPUT_SCHEMA  # noqa: E402
from tests import test_finish_haiku55 as mock_builds  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RUN = driver.RUN_NAME
SLUG = "haiku55"
HAIKU = "claude-haiku-5.5"
PINNED = driver.PINNED_INPUTS
BUNDLE = Path("publish") / RUN
SNAPSHOT_DIR = Path("paper/snapshot/20260501")
FROZEN_RUN = SNAPSHOT_DIR / "runs" / RUN
ANNOTATIONS_DIR = Path("annotations") / RUN
ADJUDICATIONS = "us_adjudications.json"
ADJUDICATIONS_PATH = ANNOTATIONS_DIR / ADJUDICATIONS
EXPLANATIONS = "us_case_reference_explanations.csv"
EXCLUSIONS = "reference_exclusions.json"
ROWS, NOTES = "us_audit_row_annotations.csv", "us_case_notes.csv"
AMENDMENTS_RECORD = f"us_{driver.AMENDMENTS}"
# The UTC day the synthetic stages' 2026-10-06 decisions were written; the
# committed spec does not name one yet (see docs/haiku55/design.md).
WRITTEN_ON = "2026-10-09"
# A real incumbent, so the freeze's incumbent prediction gate compares rows.
INCUMBENT = "claude-fable-5"
# Settings for Hypothesis tests: the autouse fixtures only patch modules, so
# sharing them across examples is safe.
PROPERTY = settings(
    deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)


def examples(count: int) -> settings:
    return settings(PROPERTY, max_examples=count)


# The synthetic stage's one judged case, an incumbent-only case kept from the
# seed, and the audit evidence the receipt must bind for it.
KEPT = "us__scenario_000__snap"
AUDIT_EVIDENCE = [Path("audit/cases.jsonl"), Path("audit/schema.json")] + [
    Path("audit/cases") / KEPT / name
    for name in ("prompt.md", "verdict.json", "verdict.meta.json")
]
ANNOTATION_CSVS = [BUNDLE / "annotations" / name for name in (ROWS, NOTES)]

# --- Git baselines ---------------------------------------------------------------

# Captured at import: a test may replace driver.base_commit_blob, and the
# caches below must hold release 20261006's bytes whatever it does.
_BASE_COMMIT_BLOB = driver.base_commit_blob
_BASE_PAYLOAD = driver.base_payload_from_commit
_HEAD_BLOB = driver.head_blob


@functools.cache
def base_blob(path: Path) -> bytes:
    """A repository file as committed at the driver's BASE_COMMIT."""
    return _BASE_COMMIT_BLOB(Path(path))


@functools.cache
def head_blob(path: Path) -> bytes:
    return _HEAD_BLOB(Path(path).as_posix())


@functools.cache
def _spec_text() -> str:
    return (REPO / driver.SPEC_PATH).read_text()


def release_spec(**changes) -> dict:
    """docs/haiku55/spec.json with the day its decisions were written."""
    spec = json.loads(_spec_text())
    spec.setdefault("adjudications_written_on", WRITTEN_ON)
    spec.update(changes)
    return spec


@functools.cache
def release_exclusions_text() -> str:
    """Release 20261006's exclusion record plus the ten ruled records."""
    base = json.loads(base_blob(FROZEN_RUN / EXCLUSIONS))
    return driver.exclusions_text(driver.build_release_exclusions(base, release_spec()))


def release_exclusions() -> list[dict]:
    return json.loads(release_exclusions_text())["exclusions"]


@functools.cache
def _base_stats_text() -> str:
    payload = _BASE_PAYLOAD()
    return json.dumps(payload["countries"]["us"]["modelStats"])


def base_stats() -> list[dict]:
    """Release 20261006's modelStats, as the base payload in git holds them."""
    return json.loads(_base_stats_text())


def base_live() -> dict:
    """The part of release 20261006's payload export reads: its modelStats."""
    return {"countries": {"us": {"modelStats": base_stats()}}}


# --- Guards ----------------------------------------------------------------------

GUARDED = (
    Path("app/src/data.artifact.json"),
    Path("app/src/data.versions.json"),
    Path("app/src/paperSnapshot.json"),
    SNAPSHOT_DIR,
    ANNOTATIONS_DIR,
    Path("app/.cache"),
)


def _tree_state() -> dict[str, tuple[int, int]]:
    state = {}
    for name in GUARDED:
        path = REPO / name
        paths = [path] if path.is_file() else sorted(path.rglob("*"))
        for item in paths:
            if item.is_file():
                stat = item.stat()
                state[str(item)] = (stat.st_size, stat.st_mtime_ns)
    return state


@pytest.fixture(scope="module", autouse=True)
def checkout_untouched():
    """No test in this module writes the checkout's tracked freeze outputs."""
    before = _tree_state()
    yield
    assert _tree_state() == before


# configure_freezer assigns these on the freeze_snapshot module itself.
CONFIGURED = (
    "SNAPSHOT_DATE",
    "SOURCE_RUN",
    "SOURCE_US",
    "SOURCE_ANNOTATIONS",
    "REFERENCE_META_SOURCE",
    "REFERENCE_PINS",
    "PUBLISHED_DASHBOARD_SOURCE",
    "PUBLISHED_DASHBOARD_ARTIFACT",
    "RUN_STATE_EVIDENCE",
    "AUDIT_CASES_DIR",
    "audit_judge_provenance",
    "developer_adjudications_block",
    "freeze_serving_configuration",
)


@pytest.fixture(autouse=True)
def no_real_freezer(monkeypatch):
    """The real freezer never runs here, and what main configures is undone."""
    import pandas as pd

    def refuse():
        raise AssertionError("a test reached the real freeze_snapshot.main")

    monkeypatch.setattr(freezer, "main", refuse)
    for name in CONFIGURED:
        monkeypatch.setattr(freezer, name, getattr(freezer, name))
    option = "future.infer_string"
    try:
        saved = pd.get_option(option)
    except (KeyError, pd.errors.OptionError):
        saved = None
    yield
    if saved is not None:
        pd.set_option(option, saved)


@pytest.fixture(autouse=True)
def spec(monkeypatch):
    """The spec every driver read sees: the committed one, with the day the
    2026-10-06 wave's decisions were written. A test may edit the dict."""
    value = release_spec()
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(value))
    return value


def point_freeze_at(workspace: Path, monkeypatch) -> None:
    """The freeze and the freezer both write into ``workspace`` only."""
    monkeypatch.setattr(release, "ROOT", workspace)
    monkeypatch.setattr(freezer, "ROOT", workspace)
    monkeypatch.setattr(freezer, "SNAPSHOT_DIR", workspace / SNAPSHOT_DIR)
    monkeypatch.setattr(freezer, "RUN_DEST", workspace / FROZEN_RUN)
    monkeypatch.setattr(freezer, "ANNOTATIONS_DEST", workspace / ANNOTATIONS_DIR)


# --- Synthetic stage -------------------------------------------------------------


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned_references(directory: Path, exclusions: str | None = None) -> Path:
    """Release 20261006's four pinned reference files, from git, and the
    release's exclusion record (or ``exclusions``), into ``directory``."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in driver.REFERENCE_FILES:
        if name == EXCLUSIONS:
            text = release_exclusions_text() if exclusions is None else exclusions
            (directory / name).write_text(text)
        else:
            (directory / name).write_bytes(base_blob(FROZEN_RUN / name))
    return directory


def base_references(directory: Path) -> Path:
    """The five reference files release 20261006 committed, from git."""
    directory.mkdir(parents=True, exist_ok=True)
    for name in driver.REFERENCE_FILES:
        (directory / name).write_bytes(base_blob(FROZEN_RUN / name))
    return directory


# The fingerprint Claude Haiku 5.5's supervised run recorded when it started
# (results/local/haiku55-runs/haiku55/run/run_state.json, 2026-10-08).
HAIKU_FINGERPRINT = {
    "fingerprint_version": 3,
    "model_id": "claude-haiku-5-5",
    "answer_contract": "tool",
    "tool_choice_mode": "forced",
    "chunk_size": None,
    "prompt_contract_version": "2026-08-09-v2-scoring-contract",
    "completion_budget_ceiling": 128000,
    "initial_completion_budget_tokens": 16384,
    "thinking": {"mode": "provider_default"},
    "request_timeout_seconds": 300,
    "max_repair_rounds": 2,
}
COLUMNS = (
    "model,scenario_id,variable,prediction,explanation,raw_response,"
    "provider_resolved_model,prompt_tokens,completion_tokens,error,"
    "estimated_cost_usd,total_cost_usd,total_tokens,elapsed_seconds,"
    "request_started_at,request_completed_at\n"
)
# Claude Haiku 5.5's run file as the synthetic stage pins it: the usage
# columns its published cost, tokens and latency come from, and the request
# times the response window is dated by (2026-10-08 UTC).
HAIKU_RUN = COLUMNS + (
    "claude-haiku-5.5,scenario_000,snap,1200.0,Used the 2026 allotment.,{},"
    "claude-haiku-5-5,4000,96,,0.0125,0.0125,4096.5,12.75,1791495690.5,"
    "1791495702.25\n"
    "claude-haiku-5.5,scenario_001,snap,0.0,Not eligible.,{},claude-haiku-5-5,"
    "3900,88,,0.011,0.011,3900.25,11.5,1791495700.0,1791495711.5\n"
)
WINDOW = "2026-06-12 to 2026-10-08"
# An incumbent row the bundle's predictions hold beside Claude Haiku 5.5's.
INCUMBENT_ROW = (
    f"{INCUMBENT},scenario_000,snap,900.0,Used the 2025 allotment.,,"
    f"{INCUMBENT},,,,,,,,,\n"
)


def restamp(stage: Path) -> None:
    """Write stage.json and model-provenance.json for the stage as it stands,
    as prepare and install-exclusions would have."""
    names = [
        BUNDLE / "us" / name for name in (*driver.REFERENCE_FILES, "predictions.csv")
    ]
    names += [Path("inputs") / SLUG / name for name in PINNED]
    files = {str(name): sha(stage / name) for name in names}
    installed = {
        "base_sha256": driver.BASE_REFERENCE_SHA256[EXCLUSIONS],
        "sha256": files[str(BUNDLE / "us" / EXCLUSIONS)],
        "spec_sha256": sha(REPO / driver.SPEC_PATH),
        "records": driver.RELEASE_EXCLUSIONS,
    }
    record = {
        "partial": False,
        "early": False,
        "base_tag": driver.BASE_TAG,
        "base_commit": driver.BASE_COMMIT,
        "files": files,
        "exclusions_installed": installed,
    }
    (stage / "stage.json").write_text(json.dumps(record))
    inputs = stage / "inputs" / SLUG
    state = json.loads((inputs / "run_state.json").read_text())
    provenance = {
        HAIKU: {
            "predictions_sha256": sha(inputs / "predictions.csv"),
            "treatment_fingerprint": state["treatment_fingerprint"],
        }
    }
    (stage / "model-provenance.json").write_text(json.dumps(provenance))


def write_inputs(stage: Path) -> dict:
    """Claude Haiku 5.5's run files, the bundle's predictions holding its rows
    as prepare folds them, and the prepare-time hashes; returns the pins."""
    inputs = stage / "inputs" / SLUG
    inputs.mkdir(parents=True, exist_ok=True)
    (inputs / "predictions.csv").write_text(HAIKU_RUN)
    state = {
        "model": HAIKU,
        "total": 100,
        "completed": 100,
        "stopped_reason": None,
        "treatment_fingerprint": HAIKU_FINGERPRINT,
    }
    (inputs / "run_state.json").write_text(json.dumps(state))
    header, *rows = HAIKU_RUN.splitlines(keepends=True)
    (stage / BUNDLE / "us/predictions.csv").write_text(
        header + INCUMBENT_ROW + "".join(rows)
    )
    restamp(stage)
    return {SLUG: {name: sha(inputs / name) for name in PINNED}}


def write_audit(audit: Path) -> None:
    """One judged, kept case with a bound seed verdict; one parse-only case,
    which is never judged and so needs no verdict."""
    case = audit / "cases" / KEPT
    case.mkdir(parents=True)
    (audit / "schema.json").write_text(json.dumps(AUDIT_OUTPUT_SCHEMA))
    manifest = [
        {
            "case_id": KEPT,
            "scenario_id": "scenario_000",
            "variable": "snap",
            "wrong_models": [INCUMBENT],
            "parse_failure_only": False,
        },
        {
            "case_id": "us__scenario_001__snap",
            "scenario_id": "scenario_001",
            "variable": "snap",
            "wrong_models": [INCUMBENT],
            "parse_failure_only": True,
        },
    ]
    (audit / "cases.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in manifest)
    )
    (case / "prompt.md").write_text("Classify these wrong answers.\n")
    verdict = {
        "reference_suspect": False,
        "reference_bug_hypothesis": "",
        "case_failure_source": "llm_error",
        "case_failure_subtype": "thresholds_rates",
        "rationale": "The model applied an outdated threshold.",
        "models": [
            {
                "model": INCUMBENT,
                "failure_source": "llm_error",
                "failure_subtype": "thresholds_rates",
                "diagnosis": "The model used the prior year's threshold.",
            }
        ],
    }
    (case / "verdict.json").write_text(json.dumps(verdict))
    (case / "verdict.meta.json").write_text(
        json.dumps(
            {
                "verdict_sha256": sha(case / "verdict.json"),
                "judge_model_requested": "default",
            }
        )
    )


def case_dir_name(scenario_id: str, variable: str) -> str:
    return f"us__{scenario_id}__{variable}"


def ruled_new_outputs() -> list[tuple[str, str]]:
    """The ruled outputs with no earlier decision: all but the restated one."""
    spec = release_spec()
    restated = {driver.spec_key(item) for item in spec["restated_adjudications"]}
    return [
        driver.spec_key(item)
        for item in spec["adjudications"]
        if driver.spec_key(item) not in restated
    ]


def write_ruled_verdicts(cases: Path) -> None:
    """A bound Opus 5.5 verdict for each newly decided ruled output, as the
    adjudicate-exclusions step reads it."""
    for index, output in enumerate(ruled_new_outputs()):
        case = cases / case_dir_name(*output)
        case.mkdir(parents=True, exist_ok=True)
        verdict = {
            "case_failure_source": "llm_error",
            "case_failure_subtype": "thresholds_rates",
            "reference_suspect": index % 2 == 0,
        }
        (case / "verdict.json").write_text(json.dumps(verdict))
        (case / "verdict.meta.json").write_text(
            json.dumps(
                {
                    "verdict_sha256": sha(case / "verdict.json"),
                    "judge_model_requested": driver.JUDGE_MODEL,
                    "judge_model_reported": [driver.JUDGE_MODEL],
                    "judged_at_utc": "2026-10-08T12:00:00+00:00",
                }
            )
        )


def ruled_record(cases: Path) -> dict:
    """Release 20261006's record with the ten ruled outputs decided, as
    --step adjudicate-exclusions writes it (scenario_051 not re-judged)."""
    return driver.exclusion_adjudications(driver.base_adjudication_record(), cases)


def write_judge_verdicts(cases: Path, record: dict) -> None:
    """For every other decided case, a verdict whose classes and flag are the
    ones its entry records the judge giving."""
    for entry in record["adjudications"]:
        case = cases / case_dir_name(entry["scenario_id"], entry["variable"])
        if (case / "verdict.json").is_file():
            continue
        case.mkdir(parents=True, exist_ok=True)
        verdict = {
            "case_failure_source": entry["judge_failure_source"],
            "case_failure_subtype": entry["judge_failure_subtype"],
            "reference_suspect": bool(entry.get("judge_reference_suspect")),
        }
        (case / "verdict.json").write_text(json.dumps(verdict))


def test_the_freeze_adds_haiku55_alone_under_the_driver_tag():
    assert release.NEW_MODELS == {SLUG: HAIKU} == driver.MODELS
    assert release.BOARD_MODELS == 47
    assert (driver.RELEASE_EXCLUSIONS, driver.RELEASE_SCORED) == (74, 1910)
    assert release.RUN == RUN


@pytest.fixture
def freeze_preflight(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    point_freeze_at(workspace, monkeypatch)
    stage = workspace / "results/local/stage"
    stage.mkdir(parents=True)
    payload = stage / "data-board47.json"
    payload.write_text(json.dumps({"countries": {"us": {"modelStats": []}}}))
    evidence = [
        BUNDLE / "us" / name for name in (*driver.REFERENCE_FILES, "predictions.csv")
    ]
    evidence += [BUNDLE / "annotations" / name for name in driver.ANNOTATION_FILES]
    evidence += [Path(driver.PROMPT_CHANGES)]
    for name in evidence:
        (stage / name).parent.mkdir(parents=True, exist_ok=True)
        (stage / name).write_text(f"Evidence: {name.name}\n")
    # install-exclusions wrote the release's record into the bundle.
    (stage / BUNDLE / "us" / EXCLUSIONS).write_text(release_exclusions_text())
    # Claude Haiku 5.5's run files are the committed pins' (stubbed here), and
    # the bundle's predictions hold its rows as prepare folded them.
    pins = write_inputs(stage)
    monkeypatch.setattr(driver, "committed_input_pins", lambda: pins)
    evidence += [Path("inputs") / SLUG / name for name in PINNED]
    evidence += [Path("model-provenance.json"), Path("stage.json")]
    write_audit(stage / "audit")
    evidence += AUDIT_EVIDENCE
    (stage / driver.PROMPT_CHANGES).write_text(
        json.dumps({"added": [], "changed": [], "kept": []})
    )
    receipt = {
        "release_tag": driver.RELEASE_TAG,
        "base_tag": driver.BASE_TAG,
        "base_sha256": driver.BASE_SHA256,
        "payload_sha256": sha(payload),
        "models": 47,
        "partial": False,
        "files": {str(name): sha(stage / name) for name in evidence},
    }
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    app = workspace / "app/src"
    app.mkdir(parents=True)
    # The live pointer and version list as release 20261006 left them.
    (app / "data.artifact.json").write_bytes(base_blob(Path(release.POINTER)))
    (app / "data.versions.json").write_bytes(base_blob(Path(release.VERSIONS)))
    return stage, payload, receipt


def workspace_files():
    return {
        path.relative_to(release.ROOT): path.read_bytes()
        for path in release.ROOT.rglob("*")
        if path.is_file()
    }


def rewrite_receipt(stage: Path, receipt: dict) -> None:
    receipt["files"] = {name: sha(stage / name) for name in receipt["files"]}
    (stage / "release-ready.json").write_text(json.dumps(receipt))


def test_freeze_rejects_pretty_json_before_any_workspace_mutation(freeze_preflight):
    stage, payload, receipt = freeze_preflight
    payload.write_text(json.dumps(json.loads(payload.read_text()), indent=2) + "\n")
    receipt["payload_sha256"] = sha(payload)
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    before = workspace_files()
    with pytest.raises(SystemExit, match="does not recombine to the freeze format"):
        release.main(["--stage-dir", str(stage)])
    assert workspace_files() == before


def test_the_default_tag_is_the_driver_release_tag(freeze_preflight, monkeypatch):
    stage, _, receipt = freeze_preflight
    monkeypatch.setattr(driver, "RELEASE_TAG", "dashboard-data-20261010")
    with pytest.raises(SystemExit, match="release tag 'dashboard-data-20261010'"):
        release.main(["--stage-dir", str(stage), "--dry-run"])
    receipt["release_tag"] = "dashboard-data-20261010"
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    # Past the receipt, the spec still names the release it was written for.
    with pytest.raises(SystemExit, match="names another release or base"):
        release.main(["--stage-dir", str(stage), "--dry-run"])


def test_a_tag_that_is_not_a_dated_release_is_refused(freeze_preflight):
    stage, _, _ = freeze_preflight
    with pytest.raises(SystemExit):
        release.main(["--stage-dir", str(stage), "--tag", "latest", "--dry-run"])


def test_the_freeze_refuses_an_unbound_MOCK_engine_upgrade(freeze_preflight):
    """MOCK: an engine name alone does not bind an installed build."""
    stage, _, receipt = freeze_preflight
    assert not release.engine_upgrade_installed(stage)
    assert not release.engine_upgrade_installed(stage / "absent")
    (stage / "stage.json").write_text(
        json.dumps({"references_installed": {"engine_version": "MOCK 2.37.1"}})
    )
    rewrite_receipt(stage, receipt)
    assert release.engine_upgrade_installed(stage)
    before = workspace_files()
    for dry_run in ([], ["--dry-run"]):
        with pytest.raises(SystemExit, match="does not bind the installed build"):
            release.main(["--stage-dir", str(stage), *dry_run])
    assert workspace_files() == before


@pytest.mark.parametrize(
    "defect",
    [
        "changed",
        "outside_stage",
        "missing_hashes",
        "board46",
        "partial",
        "tag",
        "base_tag",
        "base_sha256",
    ],
)
def test_freeze_refuses_changed_or_unbound_evidence(freeze_preflight, defect):
    stage, _, receipt = freeze_preflight
    message = "Strict export receipt does not match"
    if defect == "changed":
        (stage / "audit/cases" / KEPT / "verdict.json").write_text("Altered\n")
        message = "Staged evidence changed"
    elif defect == "outside_stage":
        path = release.ROOT / "app/src/data.artifact.json"
        receipt["files"]["../../../app/src/data.artifact.json"] = sha(path)
        message = "Staged evidence changed"
    elif defect == "missing_hashes":
        receipt["files"] = {}
        message = "missing staged evidence hashes"
    elif defect == "board46":
        receipt["models"] = 46
    elif defect == "partial":
        receipt["partial"] = True
    elif defect == "base_tag":
        receipt["base_tag"] = "dashboard-data-20260930"
        message = "does not name release 20261006 as its base"
    elif defect == "base_sha256":
        receipt["base_sha256"] = "0" * 64
        message = "does not name release 20261006 as its base"
    else:
        receipt["release_tag"] = driver.BASE_TAG
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    before = workspace_files()
    with pytest.raises(SystemExit, match=message):
        release.main(["--stage-dir", str(stage), "--dry-run"])
    assert workspace_files() == before


@pytest.mark.parametrize(
    "unbound",
    [
        str(BUNDLE / "us" / EXCLUSIONS),
        str(BUNDLE / "annotations" / ADJUDICATIONS),
        str(BUNDLE / "annotations" / EXPLANATIONS),
        f"inputs/{SLUG}/run_state.json",
        f"inputs/{SLUG}/predictions.csv",
        "model-provenance.json",
        driver.PROMPT_CHANGES,
        "stage.json",
    ],
)
def test_the_receipt_must_bind_references_adjudications_and_run_state(
    freeze_preflight, unbound
):
    stage, _, receipt = freeze_preflight
    del receipt["files"][unbound]
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    with pytest.raises(SystemExit, match="does not bind"):
        release.main(["--stage-dir", str(stage), "--dry-run"])


@pytest.mark.parametrize(
    "unbound", [str(path) for path in (*AUDIT_EVIDENCE, *ANNOTATION_CSVS)]
)
def test_the_receipt_must_bind_every_judged_case_and_both_annotation_csvs(
    freeze_preflight, unbound
):
    """Without its receipt entry, a kept verdict or sidecar could be edited
    and re-hashed after export; the freeze refuses the missing entry."""
    stage, _, receipt = freeze_preflight
    del receipt["files"][unbound]
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    before = workspace_files()
    with pytest.raises(SystemExit, match=f"does not bind.*{re.escape(unbound)}"):
        release.main(["--stage-dir", str(stage), "--dry-run"])
    assert workspace_files() == before


def test_a_judged_cases_transcript_must_be_bound(freeze_preflight):
    """An isolated judge's transcript, which the provenance gate reads, could
    otherwise be edited and re-hashed after export."""
    stage, _, receipt = freeze_preflight
    transcript = Path("audit/cases") / KEPT / "claude.transcript.jsonl"
    (stage / transcript).write_text("{}\n")
    with pytest.raises(
        SystemExit, match=f"does not bind.*{re.escape(str(transcript))}"
    ):
        release.main(["--stage-dir", str(stage), "--dry-run"])
    receipt["files"][str(transcript)] = sha(stage / transcript)
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    # Bound, it passes the receipt; the synthetic payload fails the schema.
    with pytest.raises(SystemExit, match="Strict dashboard gate failed"):
        release.main(["--stage-dir", str(stage), "--dry-run"])


def test_wording_amendments_present_in_the_stage_must_be_bound(freeze_preflight):
    stage, _, _ = freeze_preflight
    (stage / driver.AMENDMENTS).write_text(json.dumps({"amendments": []}))
    with pytest.raises(SystemExit, match=f"does not bind.*{driver.AMENDMENTS}"):
        release.main(["--stage-dir", str(stage), "--dry-run"])


# --- The spec --------------------------------------------------------------------


@pytest.mark.parametrize(
    "field, value",
    [
        ("release_tag", "dashboard-data-20261006"),
        ("base_tag", "dashboard-data-20260930"),
        ("base_sha256", "0" * 64),
    ],
)
def test_the_freeze_refuses_a_spec_for_another_release_or_base(spec, field, value):
    spec[field] = value
    with pytest.raises(SystemExit, match=f"names another release or base.*{field}"):
        release.release_spec(driver.RELEASE_TAG)


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("snapshot_date", None, "names no snapshot_date"),
        ("snapshot_date", "2026-10-32", "names no snapshot_date"),
        ("snapshot_date", 20261009, "names no snapshot_date"),
        ("adjudications_written_on", None, "names no adjudications_written_on"),
        ("adjudications_written_on", " ", "names no adjudications_written_on"),
    ],
)
def test_the_freeze_refuses_a_spec_without_its_dates(spec, field, value, message):
    if value is None:
        del spec[field]
    else:
        spec[field] = value
    with pytest.raises(SystemExit, match=message):
        release.release_spec(driver.RELEASE_TAG)


def test_the_spec_names_this_release_and_its_snapshot_date():
    value = release.release_spec(driver.RELEASE_TAG)
    assert value["snapshot_date"] == "2026-10-09"
    assert value["adjudications_written_on"] == WRITTEN_ON


def test_the_committed_spec_names_no_written_day_yet():
    """An open item (docs/haiku55/design.md): the freeze refuses the committed
    spec until it names the day the wave's decisions were written. When the
    spec gains it, this test should go."""
    committed = json.loads((REPO / driver.SPEC_PATH).read_text())
    if "adjudications_written_on" in committed:
        pytest.skip("the spec now names adjudications_written_on")
    with pytest.raises(SystemExit, match="names no adjudications_written_on"):
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(driver, "load_spec", lambda: copy.deepcopy(committed))
            release.release_spec(driver.RELEASE_TAG)


def test_a_spec_without_its_dates_stops_the_freeze_before_mutation(
    freeze_preflight, spec
):
    stage, _, _ = freeze_preflight
    del spec["adjudications_written_on"]
    before = workspace_files()
    with pytest.raises(SystemExit, match="names no adjudications_written_on"):
        release.main(["--stage-dir", str(stage)])
    assert workspace_files() == before


# --- The installed exclusions ----------------------------------------------------


def _record_installed(stage: Path, edit) -> None:
    record = json.loads((stage / "stage.json").read_text())
    edit(record)
    (stage / "stage.json").write_text(json.dumps(record))


@pytest.mark.parametrize(
    "defect, message",
    [
        ("base_record", "is not release 20261006's record plus the 10 ruled"),
        ("ruled_record_edited", "is not release 20261006's record plus the 10 ruled"),
        ("receipt_hash", "Staged evidence changed since strict export.*exclusions"),
        ("not_installed", "stage.json does not record the release's 74"),
        ("wrong_count", "stage.json does not record the release's 74"),
        ("wrong_base", "stage.json does not record the release's 74"),
        ("stale_files", "stage.json does not record the release's 74"),
    ],
)
def test_the_freeze_refuses_a_stage_without_the_installed_exclusions(
    freeze_preflight, defect, message
):
    """The stage must score on the release's record, as install-exclusions
    wrote it: its bytes, its receipt hash and its stage.json record."""
    stage, _, receipt = freeze_preflight
    staged = stage / BUNDLE / "us" / EXCLUSIONS
    if defect == "base_record":
        staged.write_bytes(base_blob(FROZEN_RUN / EXCLUSIONS))
    elif defect == "ruled_record_edited":
        doc = json.loads(staged.read_text())
        doc["exclusions"][-2]["frozen_value"] += 1
        staged.write_text(driver.exclusions_text(doc))
    if defect in ("base_record", "ruled_record_edited"):
        # Every hash follows the edit: stage.json's and the receipt's.
        restamp(stage)
        rewrite_receipt(stage, receipt)
    elif defect == "receipt_hash":
        receipt["files"][str(BUNDLE / "us" / EXCLUSIONS)] = "0" * 64
        (stage / "release-ready.json").write_text(json.dumps(receipt))
    else:
        edits = {
            "not_installed": lambda r: r.pop("exclusions_installed"),
            "wrong_count": lambda r: r["exclusions_installed"].update(records=64),
            "wrong_base": lambda r: r["exclusions_installed"].update(
                base_sha256="0" * 64
            ),
            "stale_files": lambda r: r["files"].update(
                {
                    str(BUNDLE / "us" / EXCLUSIONS): driver.BASE_REFERENCE_SHA256[
                        EXCLUSIONS
                    ]
                }
            ),
        }
        _record_installed(stage, edits[defect])
        rewrite_receipt(stage, receipt)
    before = workspace_files()
    with pytest.raises(SystemExit, match=message):
        release.main(["--stage-dir", str(stage), "--dry-run"])
    assert workspace_files() == before


def test_the_receipt_must_bind_the_installed_record(freeze_preflight):
    """verify_receipt already refuses a receipt hash the staged file does not
    have; the installed-exclusions gate checks the binding on its own too."""
    stage, _, receipt = freeze_preflight
    text = release_exclusions_text()
    expected = hashlib.sha256(text.encode()).hexdigest()
    assert release.verify_installed_exclusions(stage, receipt, text) == expected
    receipt["files"][str(BUNDLE / "us" / EXCLUSIONS)] = "0" * 64
    with pytest.raises(SystemExit, match="does not bind the installed"):
        release.verify_installed_exclusions(stage, receipt, text)


def test_the_installed_record_is_the_one_the_live_stage_holds():
    """The live stage, read only, holds the record the freeze requires
    (local: the stage is gitignored)."""
    stage = REPO / "results/local/release-haiku55/stage"
    staged = stage / BUNDLE / "us" / EXCLUSIONS
    if not staged.is_file():
        pytest.skip("no live stage in this checkout")
    installed = (
        json.loads((stage / "stage.json").read_text()).get("exclusions_installed") or {}
    )
    if installed.get("spec_sha256") != sha(driver.ROOT / driver.SPEC_PATH):
        pytest.skip("the 2.15.17 fallback stage was installed under an earlier spec")
    receipt = {"files": {str(BUNDLE / "us" / EXCLUSIONS): sha(staged)}}
    assert (
        release.verify_installed_exclusions(stage, receipt, release_exclusions_text())
        == hashlib.sha256(release_exclusions_text().encode()).hexdigest()
    )


def _payload_country(exclusions: list[dict], n: int = 1910) -> dict:
    return {
        "referenceExclusions": [
            {"scenarioId": r["scenario_id"], "variable": r["variable"]}
            for r in exclusions
        ],
        "modelStats": [{"model": "a", "n": n}, {"model": HAIKU, "n": n}],
    }


def test_the_payload_must_list_the_releases_exclusions_in_order():
    records = release_exclusions()
    release.verify_scored_outputs(_payload_country(records), records)
    swapped = records[:]
    swapped[0], swapped[1] = swapped[1], swapped[0]
    with pytest.raises(SystemExit, match="their order"):
        release.verify_scored_outputs(_payload_country(swapped), records)
    with pytest.raises(
        SystemExit, match="73 excluded outputs are not the release's 74"
    ):
        release.verify_scored_outputs(_payload_country(records[:-1]), records)
    base = json.loads(base_blob(FROZEN_RUN / EXCLUSIONS))["exclusions"]
    with pytest.raises(SystemExit, match="64 excluded outputs"):
        release.verify_scored_outputs(_payload_country(base), records)


def test_every_model_must_be_scored_on_1910_outputs():
    records = release_exclusions()
    country = _payload_country(records)
    country["modelStats"][1]["n"] = 1920
    with pytest.raises(SystemExit, match=f"scored on 1910 outputs.*{HAIKU}': 1920"):
        release.verify_scored_outputs(country, records)


# --- The staged board ------------------------------------------------------------

# One unadjudicated case of the synthetic payload, as two models answered it.
CASE = ("scenario_017", "snap")


def _case_row(prediction: float) -> dict:
    return {
        "prediction": prediction,
        "groundTruth": 1200.0,
        "scored": True,
        "annotation": "Used the prior year's allotment.",
        "failureSource": "llm_error",
        "failureSubtype": "thresholds_rates",
        "caseAnnotation": "Both models used the prior year's maximum allotment.",
        "caseFailureSources": "llm_error",
        "caseFailureSubtypes": "thresholds_rates",
    }


def _without_carried_usage(board: dict) -> dict:
    """``board`` as export_full_run returns it: Fable 5's usage not carried."""
    board = copy.deepcopy(board)
    fable = next(
        row
        for row in board["countries"]["us"]["modelStats"]
        if row["model"] == "claude-fable-5"
    )
    fable.update(costUsd=0.0, costPerHousehold=0.0)
    del fable["totalTokens"], fable["latencySeconds"]
    return board


@pytest.fixture
def rebuilds():
    """Each bundle an export stub read: (which board, its directory, its files)."""
    return []


@pytest.fixture
def exports():
    """The boards the stubbed export_full_run returns: "release" for the
    staged bundle, "scope" when export puts release 20261006's exclusion
    record back. A test that edits a bundle input edits them as export would
    rebuild them."""
    return {}


@pytest.fixture
def staged_board(freeze_preflight, monkeypatch, rebuilds, exports):
    """A 47-row payload past the receipt, with release 20261006's snapshot in
    the workspace.

    export_full_run is stubbed to return what it would for the bound bundle:
    with the release's 74 exclusions every model is scored on 1,910 outputs
    and one incumbent's exact match moves; with release 20261006's record put
    back the incumbents' rows are that release's. The freeze's rebuild runs
    export's own build (scope check included) on it, so an unedited payload
    rebuilds, and each test that stops at a later gate still reaches it.
    Like the real exporter, the stub writes data.json into the bundle it reads.
    """
    import policybench.dashboard_schema
    import policybench.full_run_export

    stage, payload, receipt = freeze_preflight
    # A synthetic stage binds no seed; the re-derived case list is tested in
    # test_finish_haiku55.py.
    monkeypatch.setattr(driver, "rejudged_cases", lambda stage: frozenset())
    # The seed stage.json binds is the synthetic audit as written: its one
    # judged case is kept, so its verdict must stay the seed's.
    seed = driver.seed_digest(stage / "audit")
    monkeypatch.setattr(driver, "load_seed", lambda stage: seed)
    monkeypatch.setattr(driver, "base_payload_from_commit", base_live)
    snapshot = release.ROOT / SNAPSHOT_DIR
    # The snapshot release 20261006 committed, from BASE_COMMIT.
    snapshot.mkdir(parents=True)
    for name in ("manifest.json", "model_serving_config.json"):
        (snapshot / name).write_bytes(base_blob(SNAPSHOT_DIR / name))
    base_references(release.ROOT / FROZEN_RUN)
    (snapshot / "us_reference_outputs.csv").write_bytes(
        base_blob(FROZEN_RUN / "reference_outputs.csv")
    )
    # prepare copies the committed reference explanations; no step writes them.
    (stage / BUNDLE / "annotations" / EXPLANATIONS).write_bytes(
        base_blob(ANNOTATIONS_DIR / EXPLANATIONS)
    )
    haiku = {
        "model": HAIKU,
        "condition": "no_tools",
        "exact": 58.25,
        "score": 71.5,
        "n": driver.RELEASE_SCORED,
    }
    scenario, variable = CASE
    cases = {
        scenario: {variable: {INCUMBENT: _case_row(900.0), HAIKU: _case_row(950.0)}}
    }

    def board(stats, exclusions):
        country = {
            "referenceExclusions": [
                {"scenarioId": r["scenario_id"], "variable": r["variable"]}
                for r in exclusions
            ],
            "modelStats": stats,
            "scenarioPredictions": copy.deepcopy(cases),
        }
        return {"countries": {"us": country}}

    released = base_stats()
    for row in released:
        row["n"] = driver.RELEASE_SCORED
    # The ten records move one incumbent's exact match.
    released[1]["exact"] += 0.5
    staged = board([*released, haiku], release_exclusions())
    payload.write_text(json.dumps(staged))
    base_exclusions = json.loads(base_blob(FROZEN_RUN / EXCLUSIONS))["exclusions"]
    scoped = board([*base_stats(), {**haiku, "n": 1920}], base_exclusions)
    exports["release"] = _without_carried_usage(staged)
    exports["scope"] = _without_carried_usage(scoped)
    monkeypatch.setattr(
        policybench.dashboard_schema, "validate_dashboard_payload", lambda *a, **k: []
    )

    def export_full_run(run_dir, *, countries, skip_app_data):
        assert countries == ["us"] and skip_app_data
        run_dir = Path(run_dir)
        files = {
            path.relative_to(run_dir): path.read_bytes()
            for path in run_dir.rglob("*")
            if path.is_file()
        }
        records = json.loads(files[Path("us") / EXCLUSIONS])["exclusions"]
        which = "scope" if len(records) == driver.BASE_EXCLUSIONS else "release"
        rebuilds.append((which, run_dir, files))
        (run_dir / "data.json").write_text("Fable 5's usage is not carried here.\n")
        return copy.deepcopy(exports[which])

    monkeypatch.setattr(policybench.full_run_export, "export_full_run", export_full_run)

    # The synthetic stage re-opens no case, so its provenance record lists none.
    record = stage.parent / "judge_provenance.json"
    record.write_text(json.dumps({"note": "None.", "counts": {}, "verdicts": []}))
    monkeypatch.setattr(driver, "JUDGE_PROVENANCE", record)

    def rebind(restamp_stage=True, bind=()):
        # Every hash in the stage follows the edit: the receipt's and, unless
        # a test keeps them, stage.json's and model-provenance.json's.
        if restamp_stage:
            restamp(stage)
        for path in bind:
            receipt["files"][str(path)] = ""
        receipt["payload_sha256"] = sha(payload)
        receipt["judge_provenance"] = {
            "path": driver.JUDGE_PROVENANCE_PATH,
            "sha256": sha(record),
        }
        rewrite_receipt(stage, receipt)

    rebind()
    return stage, rebind


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("defect", ["edited", "unbound", "other_path", "missing"])
def test_the_freeze_refuses_a_provenance_record_export_did_not_bind(
    staged_board, defect, dry_run
):
    """Export binds the judge provenance record's hash in the receipt. A
    record edited afterwards, one the receipt does not bind or binds under
    another path, or a missing one, is refused before any workspace mutation."""
    stage, rebind = staged_board
    pinned_references(stage / BUNDLE / "us")
    rebind()
    receipt = json.loads((stage / "release-ready.json").read_text())
    if defect == "edited":
        driver.JUDGE_PROVENANCE.write_text(
            json.dumps({"note": "every judge ran isolated", "verdicts": []})
        )
    elif defect == "missing":
        driver.JUDGE_PROVENANCE.unlink()
    elif defect == "unbound":
        del receipt["judge_provenance"]
    else:
        receipt["judge_provenance"]["path"] = "docs/elsewhere.json"
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    before = workspace_files()
    with pytest.raises(SystemExit, match="not the judge provenance record"):
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before


@pytest.mark.parametrize("dry_run", [True, False])
def test_the_freeze_refuses_incumbent_stats_edited_after_export(staged_board, dry_run):
    """An incumbent's cost edited in the staged payload after export, with the
    receipt's payload hash updated to match, is refused before any workspace
    mutation: export's rebuild from the bound bundle does not give it."""
    stage, rebind = staged_board
    pinned_references(stage / BUNDLE / "us")
    payload = stage / "data-board47.json"
    board = json.loads(payload.read_text())
    index, row = next(
        (index, row)
        for index, row in enumerate(board["countries"]["us"]["modelStats"])
        if row["model"] not in (HAIKU, "claude-fable-5")
    )
    row["costUsd"] *= 2
    payload.write_text(json.dumps(board))
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match="is not what export builds") as refused:
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    at = f"payload.countries.us.modelStats[{index} {row['model']}].costUsd"
    assert repr(at) in str(refused.value)
    assert workspace_files() == before


@pytest.mark.parametrize("dry_run", [True, False])
def test_the_scope_check_refuses_an_incumbent_change_the_ten_records_do_not_explain(
    staged_board, exports, dry_run
):
    """An incumbent's cost changed in the bundle itself, so that export
    rebuilds the staged payload, still leaves the release: with release
    20261006's exclusion record put back, that incumbent is not release
    20261006's, byte for byte."""
    stage, rebind = staged_board
    pinned_references(stage / BUNDLE / "us")
    payload = stage / "data-board47.json"
    board = json.loads(payload.read_text())
    index, model = next(
        (index, row["model"])
        for index, row in enumerate(board["countries"]["us"]["modelStats"])
        if row["model"] not in (HAIKU, "claude-fable-5")
    )
    for target in (board, exports["release"], exports["scope"]):
        row = target["countries"]["us"]["modelStats"][index]
        assert row["model"] == model
        row["costUsd"] *= 2
    payload.write_text(json.dumps(board))
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match=f"incumbent modelStats drift.*{model}"):
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before


def _edit_new_model_scores(board: dict) -> list[str]:
    stats = board["countries"]["us"]["modelStats"]
    row = next(r for r in stats if r["model"] == HAIKU)
    row.update(exact=100.0, score=100.0)
    at = f"payload.countries.us.modelStats[{stats.index(row)} {HAIKU}]"
    return [f"{at}.exact", f"{at}.score"]


def _edit_case_review(board: dict) -> list[str]:
    scenario, variable = CASE
    case = board["countries"]["us"]["scenarioPredictions"][scenario][variable]
    for row in case.values():
        row.update(
            caseFailureSources="needs_review",
            reference_suspect=True,
            wrong_model_count=999,
        )
    at = f"payload.countries.us.scenarioPredictions.{scenario}.{variable}"
    return [
        f"{at}.{INCUMBENT}.caseFailureSources",
        f"{at}.{INCUMBENT}.reference_suspect (only staged)",
        f"{at}.{INCUMBENT}.wrong_model_count (only staged)",
    ]


def _edit_exclusion_text(board: dict) -> list[str]:
    item = board["countries"]["us"]["referenceExclusions"][-2]
    item["note"] = "A note no record carries."
    return ["payload.countries.us.referenceExclusions[72].note (only staged)"]


# Edits to the staged payload, each of which passes every other gate once the
# receipt's payload hash is updated to match.
PAYLOAD_EDITS = {
    "new_model_scores": _edit_new_model_scores,
    "case_review": _edit_case_review,
    "exclusion_text": _edit_exclusion_text,
}


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("edit", PAYLOAD_EDITS)
def test_the_freeze_refuses_a_payload_edited_after_export(staged_board, edit, dry_run):
    """The receipt binds the payload only by a hash beside it. Claude Haiku
    5.5's exact and score set to 100, a case marked needs_review, or an
    exclusion given a note no record carries, with the receipt's payload hash
    updated to match, is refused before any workspace mutation: the payload
    export builds from the bound bundle is not the staged one."""
    stage, rebind = staged_board
    pinned_references(stage / BUNDLE / "us")
    payload = stage / "data-board47.json"
    board = json.loads(payload.read_text())
    paths = PAYLOAD_EDITS[edit](board)
    payload.write_text(json.dumps(board))
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match="is not what export builds") as refused:
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    for path in paths:
        assert repr(path) in str(refused.value)
    assert workspace_files() == before


def test_the_rebuild_reads_a_scratch_copy_of_the_bound_bundle(
    staged_board, rebuilds, monkeypatch
):
    """export_full_run writes into the bundle it reads. The rebuild hands it a
    scratch copy outside the workspace holding exactly the bundle files the
    receipt binds, with their bound bytes, and removes it; the scope check
    exports a second copy with release 20261006's exclusion record. An
    unedited payload rebuilds, carrying Fable 5's usage as export does, and
    the freeze goes on to its next gate."""
    stage, rebind = staged_board
    pinned_references(stage / BUNDLE / "us")
    rebind()

    def next_gate(stage):
        raise SystemExit("Reached the verdict gate")

    monkeypatch.setattr(release, "verify_verdicts", next_gate)
    receipt = json.loads((stage / "release-ready.json").read_text())
    before = workspace_files()
    with pytest.raises(SystemExit, match="Reached the verdict gate"):
        release.main(["--stage-dir", str(stage), "--dry-run"])
    assert workspace_files() == before
    [(first, run_dir, files), (second, scope_dir, scope_files)] = rebuilds
    assert (first, second) == ("release", "scope")
    for directory in (run_dir, scope_dir):
        assert directory.name == RUN and not directory.exists()
        assert not directory.is_relative_to(release.ROOT)
    bound = [Path(name) for name in receipt["files"]]
    assert files == {
        name.relative_to(BUNDLE): (stage / name).read_bytes()
        for name in bound
        if name.is_relative_to(BUNDLE)
    }
    assert len(files) == 10
    expected = {Path(name): files[Path(name)] for name in release_inputs_for_scope()}
    expected[Path("us") / EXCLUSIONS] = driver.exclusions_text(
        json.loads(base_blob(FROZEN_RUN / EXCLUSIONS))
    ).encode()
    assert scope_files == expected


def release_inputs_for_scope() -> tuple[str, ...]:
    from release_20261006 import EXPORT_INPUTS

    return EXPORT_INPUTS


def test_the_rebuild_reads_only_the_bytes_the_receipt_binds(staged_board, rebuilds):
    """A bound bundle file that changes after the receipt was checked is
    refused rather than exported."""
    stage, rebind = staged_board
    payload = stage / "data-board47.json"
    receipt = json.loads((stage / "release-ready.json").read_text())
    base = driver.base_payload_from_commit()
    release.rebuild_payload(stage, receipt, payload, base)
    (stage / BUNDLE / "us/predictions.csv").write_text("Edited after the check.\n")
    with pytest.raises(SystemExit, match="changed since strict export.*predictions"):
        release.rebuild_payload(stage, receipt, payload, base)
    assert [which for which, *_ in rebuilds] == ["release", "scope"]


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


@examples(400)
@given(a=JSON_VALUES, b=JSON_VALUES, swap=st.booleans())
def test_payload_differences_are_empty_exactly_when_the_bytes_match(a, b, swap):
    """The freeze refuses on bytes and names paths from the parsed values; the
    two agree, key order, 1 against 1.0, True against 1 and -0.0 included."""
    if swap and isinstance(a, dict):
        b = dict(reversed(list(a.items())))
    differ = release.payload_differences(a, b)
    assert (differ == []) == (json.dumps(a) == json.dumps(b))
    assert len(differ) <= 5


def test_payload_differences_name_the_first_differing_paths():
    rebuilt = {"rows": [{"model": "m", "x": 1, "y": [1, 2]}], "z": True}
    staged = {"z": 1, "rows": [{"model": "m", "y": [1], "x": 1.0, "w": 0}]}
    assert release.payload_differences(rebuilt, staged) == [
        "payload.rows[0 m].x",
        "payload.rows[0 m].y (length 2 rebuilt, 1 staged)",
        "payload.rows[0 m].w (only staged)",
        "payload.z",
        "payload (key order)",
    ]


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("defect", ["edited_kept", "unbound_new"])
def test_the_freeze_refuses_a_verdict_edited_after_export(
    staged_board, monkeypatch, defect, dry_run
):
    """Export validates the verdicts before it writes the receipt. A kept
    verdict edited afterwards, its classes kept, its sidecar and its receipt
    entry re-hashed, must still be refused before any workspace mutation; so
    must a verdict the seed does not carry that is bound to no prompt."""
    stage, rebind = staged_board
    pinned_references(stage / BUNDLE / "us")
    case = stage / "audit/cases" / KEPT
    if defect == "edited_kept":
        verdict = json.loads((case / "verdict.json").read_text())
        verdict["rationale"] = "A rationale the judge never wrote."
        verdict["models"][0]["diagnosis"] = "A diagnosis the judge never wrote."
        (case / "verdict.json").write_text(json.dumps(verdict))
        meta = json.loads((case / "verdict.meta.json").read_text())
        meta["verdict_sha256"] = sha(case / "verdict.json")
        (case / "verdict.meta.json").write_text(json.dumps(meta))
        message = f"carried-over verdicts differ.*{KEPT}"
    else:
        monkeypatch.setattr(driver, "load_seed", lambda stage: {})
        message = f"fail validation.*{KEPT}"
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match=message):
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before


def _double_cost(frame, rows) -> list[str]:
    columns = ["estimated_cost_usd", "total_cost_usd"]
    for column in columns:
        frame.loc[rows, column] = (frame.loc[rows, column].astype(float) * 2).map(str)
    return columns


def _slower(frame, rows) -> list[str]:
    frame.loc[rows, "elapsed_seconds"] = "99.0"
    return ["elapsed_seconds"]


USAGE_EDITS = {"cost": _double_cost, "elapsed_seconds": _slower}


def _edit_haiku_rows(path: Path, edit) -> list[str]:
    import pandas as pd

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    columns = edit(frame, frame["model"] == HAIKU)
    frame.to_csv(path, index=False)
    return columns


def _republish_haiku_usage(stage: Path, exports: dict) -> None:
    """The payload as export would rebuild it from the edited predictions:
    Claude Haiku 5.5's costUsd changes, and the export stub agrees."""
    payload = stage / "data-board47.json"
    board = json.loads(payload.read_text())
    for target in (board, exports["release"], exports["scope"]):
        stats = target["countries"]["us"]["modelStats"]
        next(row for row in stats if row["model"] == HAIKU)["costUsd"] = 2.0
    payload.write_text(json.dumps(board))


@pytest.mark.parametrize("dry_run", [True, False])
@pytest.mark.parametrize("edit", USAGE_EDITS)
def test_the_freeze_refuses_new_model_usage_edited_in_the_bundle(
    staged_board, exports, edit, dry_run
):
    """Claude Haiku 5.5's cost columns doubled, or its elapsed_seconds
    changed, in the bundle's predictions, with the payload rebuilt to match
    and every hash in the stage updated (the receipt's, stage.json's and
    model-provenance.json's), is refused before any workspace mutation: its
    rows must be its pinned run file's in every column."""
    stage, rebind = staged_board
    columns = _edit_haiku_rows(stage / BUNDLE / "us/predictions.csv", USAGE_EDITS[edit])
    _republish_haiku_usage(stage, exports)
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match="not the pinned run's") as refused:
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    for column in columns:
        assert f"{HAIKU} {column} differs from the run on 2 rows" in str(refused.value)
    assert workspace_files() == before


@pytest.mark.parametrize("dry_run", [True, False])
def test_the_freeze_refuses_a_new_model_input_edited_with_the_bundle(
    staged_board, exports, dry_run
):
    """The staged run file edited together with the bundle's rows, every
    stage hash following, is not the run file the committed pins name."""
    stage, rebind = staged_board
    for path in (
        stage / "inputs" / SLUG / "predictions.csv",
        stage / BUNDLE / "us/predictions.csv",
    ):
        _edit_haiku_rows(path, _double_cost)
    _republish_haiku_usage(stage, exports)
    rebind()
    before = workspace_files()
    with pytest.raises(
        SystemExit, match=f"staged inputs/{SLUG}/predictions.csv is not the run file"
    ):
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before


def _edit_json(path: Path, edit) -> None:
    value = json.loads(path.read_text())
    edit(value)
    path.write_text(json.dumps(value))


@pytest.mark.parametrize(
    "defect",
    ["stale_stage_json", "unrecorded_input", "provenance_hash", "fingerprint"],
)
def test_the_freeze_rechecks_the_prepare_time_hashes(staged_board, defect):
    """stage.json and model-provenance.json, both bound by the receipt, must
    still describe the staged inputs."""
    stage, rebind = staged_board
    if defect == "stale_stage_json":
        path = stage / BUNDLE / "us/predictions.csv"
        path.write_text(path.read_text().replace(INCUMBENT_ROW, INCUMBENT_ROW * 2))
        message = f"changed since prepare: {BUNDLE}/us/predictions.csv"
    elif defect == "unrecorded_input":
        _edit_json(
            stage / "stage.json",
            lambda record: record["files"].pop(f"inputs/{SLUG}/predictions.csv"),
        )
        message = f"stage.json does not record.*inputs/{SLUG}/predictions.csv"
    elif defect == "provenance_hash":
        _edit_json(
            stage / "model-provenance.json",
            lambda record: record[HAIKU].update(predictions_sha256="0" * 64),
        )
        message = "model-provenance.json disagrees with the staged run"
    else:
        _edit_json(
            stage / "model-provenance.json",
            lambda record: record[HAIKU]["treatment_fingerprint"].update(
                request_timeout_seconds=600
            ),
        )
        message = "model-provenance.json disagrees with the staged run"
    rebind(restamp_stage=False)
    before = workspace_files()
    with pytest.raises(SystemExit, match=message):
        release.main(["--stage-dir", str(stage), "--dry-run"])
    assert workspace_files() == before


def _publish_annotations(stage: Path) -> None:
    """The row annotations and case notes triage publishes for the synthetic
    audit, with a staged record that decides none of its cases."""
    from policybench.audit import collect_audit

    annotations = stage / BUNDLE / "annotations"
    (annotations / ADJUDICATIONS).write_text(json.dumps({"adjudications": []}))
    collected = collect_audit(stage / BUNDLE / "us", stage / "audit")
    cases = collected["case"].rename(
        columns={
            "case_failure_source": "case_failure_sources",
            "case_failure_subtype": "case_failure_subtypes",
        }
    )
    for name, frame in ((ROWS, collected["row"]), (NOTES, cases)):
        frame.to_csv(annotations / name, index=False)


@pytest.fixture
def annotated_board(staged_board, monkeypatch):
    """The synthetic stage with release 20261006's references and the release's
    exclusion record, and the annotations triage publishes, past every gate up
    to the annotation gate; the next gate, the incumbents' predictions, stops
    the freeze. The kept case is decided by no adjudication. The record gate
    reads release 20261006's 77 decisions, which the synthetic audit lacks;
    it is tested on its own."""
    stage, rebind = staged_board
    pinned_references(stage / BUNDLE / "us")
    monkeypatch.setattr(release, "verify_adjudication_record", lambda *a, **k: 0)
    _publish_annotations(stage)

    def next_gate():
        raise SystemExit("Reached the prediction gate")

    monkeypatch.setattr(release, "base_prediction_rows", next_gate)
    rebind()
    return stage, rebind


def test_the_annotations_triage_publishes_pass_the_annotation_gate(annotated_board):
    stage, _ = annotated_board
    with pytest.raises(SystemExit, match="Reached the prediction gate"):
        release.main(["--stage-dir", str(stage), "--dry-run"])


@pytest.mark.parametrize("dry_run", [True, False])
def test_the_freeze_refuses_a_failure_class_no_judge_gave(
    annotated_board, exports, dry_run
):
    """A row's failure_source and its case note's case_failure_sources changed
    on the kept case, which no adjudication decides, with the payload rebuilt
    to carry the new class (export's rebuild agrees) and the receipt hashes
    of both CSVs and the payload updated, are refused before any workspace
    mutation."""
    import pandas as pd

    stage, rebind = annotated_board
    annotations = stage / BUNDLE / "annotations"
    for name, column in ((ROWS, "failure_source"), (NOTES, "case_failure_sources")):
        frame = pd.read_csv(annotations / name, dtype=str, keep_default_na=False)
        kept = frame.scenario_id == "scenario_000"
        assert list(frame.loc[kept, column]) == ["llm_error"]
        frame.loc[kept, column] = "prompt_ambiguity"
        frame.to_csv(annotations / name, index=False)
    payload = stage / "data-board47.json"
    board = json.loads(payload.read_text())
    scenario, variable = CASE
    for target in (board, exports["release"], exports["scope"]):
        for row in target["countries"]["us"]["scenarioPredictions"][scenario][
            variable
        ].values():
            row.update(
                failureSource="prompt_ambiguity", caseFailureSources="prompt_ambiguity"
            )
    payload.write_text(json.dumps(board))
    rebind()
    before = workspace_files()
    with pytest.raises(
        SystemExit,
        match=r"us_case_notes\.csv is not what triage builds.*"
        r"us__scenario_000__snap case_failure_sources",
    ):
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before


def test_the_freeze_refuses_a_revised_staged_reference_before_mutation(staged_board):
    stage, _ = staged_board
    before = workspace_files()
    with pytest.raises(SystemExit, match="Staged reference_outputs.csv changed"):
        release.main(["--stage-dir", str(stage)])
    assert workspace_files() == before


@pytest.mark.parametrize("dry_run", [True, False])
def test_a_reworded_explanation_is_refused(staged_board, dry_run):
    """The judge's prompt and the payload carry the reference explanations;
    this release rewords none, so a staged edit is refused before any
    workspace mutation, whatever hashes follow it."""
    stage, rebind = staged_board
    pinned_references(stage / BUNDLE / "us")
    path = stage / BUNDLE / "annotations" / EXPLANATIONS
    path.write_bytes(path.read_bytes().replace(b"the ", b"thee ", 1))
    rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match=f"Staged {EXPLANATIONS} changed"):
        release.main(["--stage-dir", str(stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before


def _stage_ruled_record(stage: Path, edit=None) -> dict:
    """The staged record as adjudicate-exclusions writes it, its new ruled
    cases' bound verdicts in the stage's audit tree; ``edit`` changes it."""
    cases = stage / "audit/cases"
    write_ruled_verdicts(cases)
    record = ruled_record(cases)
    if edit is not None:
        edit(record)
    (stage / BUNDLE / "annotations" / ADJUDICATIONS).write_text(
        driver.record_text(record)
    )
    return record


def _drop_an_unruled_decision(record: dict) -> None:
    record["adjudications"].remove(_unruled(record)[0])


def _ruled_case_files(stage: Path) -> list[Path]:
    cases = stage / "audit/cases"
    return [
        path.relative_to(stage)
        for output in ruled_new_outputs()
        for path in sorted((cases / case_dir_name(*output)).iterdir())
    ]


def test_the_freeze_refuses_a_dropped_adjudication_before_mutation(staged_board):
    stage, rebind = staged_board
    pinned_references(stage / BUNDLE / "us")
    _stage_ruled_record(stage, _drop_an_unruled_decision)
    rebind(bind=_ruled_case_files(stage))
    before = workspace_files()
    with pytest.raises(SystemExit, match="drop recorded decisions"):
        release.main(["--stage-dir", str(stage)])
    assert workspace_files() == before


def test_the_freeze_refuses_an_undecided_ruled_output_before_mutation(staged_board):
    """The record export bound must decide each ruled output as the spec says."""
    stage, rebind = staged_board
    pinned_references(stage / BUNDLE / "us")
    _stage_ruled_record(stage, lambda record: record["adjudications"].pop())
    rebind(bind=_ruled_case_files(stage))
    before = workspace_files()
    with pytest.raises(SystemExit, match="ruled outputs.*no staged decision"):
        release.main(["--stage-dir", str(stage)])
    assert workspace_files() == before


def test_the_freeze_baseline_is_release_20261006_in_git_not_the_working_tree(
    staged_board,
):
    """A freeze that stopped after copying the staged record over the committed
    one leaves them equal; the next freeze must still compare with git."""
    stage, rebind = staged_board
    pinned_references(stage / BUNDLE / "us")
    _stage_ruled_record(stage, _drop_an_unruled_decision)
    rebind(bind=_ruled_case_files(stage))
    staged = stage / BUNDLE / "annotations" / ADJUDICATIONS
    # What a partial freeze leaves behind: the working-tree record is the
    # staged one, byte for byte.
    freezer.ANNOTATIONS_DEST.mkdir(parents=True)
    shutil.copyfile(staged, freezer.ANNOTATIONS_DEST / ADJUDICATIONS)
    with pytest.raises(SystemExit, match="drop recorded decisions"):
        release.main(["--stage-dir", str(stage), "--dry-run"])


# --- A releasable board, frozen ----------------------------------------------------


def _serving_from_the_registry(destination: Path) -> None:
    """What freeze_serving_configuration writes in a checkout without the
    historical run directories: every incumbent registry-backed, and Claude
    Haiku 5.5 backed by its run state."""
    base = json.loads(base_blob(SNAPSHOT_DIR / "model_serving_config.json"))
    serving = copy.deepcopy(base)
    for row in serving["models"].values():
        row["evidence"] = {"kind": "registry"}
    serving["models"][HAIKU] = {
        **copy.deepcopy(base["models"][INCUMBENT]),
        "provider_id": "claude-haiku-5-5",
        "evidence": {"kind": "run_state", "run": "somewhere/else"},
    }
    serving["evidence_summary"] = {"registry": 46, "run_state": 1}
    serving["registry_commit"] = "the freezer's commit"
    destination.write_text(json.dumps(serving, indent=2, sort_keys=True) + "\n")


def _fake_freezer_main(calls: list, defects: set):
    """Stand-in for freeze_snapshot.main: it writes what the freezer writes,
    from where the freeze configured it, as freeze_run, freeze_annotations,
    freeze_committed_artifacts and build_manifest do, with ``defects``
    applied, and records the configuration it found."""

    def main() -> None:
        calls.append(
            {
                name: getattr(freezer, name)
                for name in (
                    "SNAPSHOT_DATE",
                    "SOURCE_RUN",
                    "SOURCE_US",
                    "SOURCE_ANNOTATIONS",
                    "REFERENCE_META_SOURCE",
                    "PUBLISHED_DASHBOARD_SOURCE",
                    "PUBLISHED_DASHBOARD_ARTIFACT",
                    "RUN_STATE_EVIDENCE",
                    "AUDIT_CASES_DIR",
                )
            }
        )
        window = freezer.model_response_window(
            freezer.SOURCE_US / "predictions.csv",
            freezer.MODEL_RESPONSE_START,
            freezer.MODEL_RESPONSE_DATE,
        )
        run = freezer.RUN_DEST
        if run.exists():
            shutil.rmtree(run)
        run.mkdir(parents=True)
        for name in ("scenarios.csv", "scenarios.csv.meta.json"):
            freezer.copy_exact(freezer.SOURCE_US / name, run / name)
        for name in ("reference_outputs.csv", EXCLUSIONS):
            freezer.copy_exact(freezer.SOURCE_US / name, run / name)
        (run / "reference_outputs.csv.meta.json").write_bytes(
            freezer.REFERENCE_META_SOURCE.read_bytes()
        )
        if freezer.REFERENCE_PINS is not None:
            freezer.copy_exact(
                freezer.SOURCE_US / "reference_outputs.csv",
                freezer.SNAPSHOT_DIR / "us_reference_outputs.csv",
            )
        if "base_exclusions" in defects:
            (run / EXCLUSIONS).write_bytes(base_blob(FROZEN_RUN / EXCLUSIONS))
        freezer.gzip_deterministic(
            freezer.SOURCE_US / "predictions.csv",
            run / "predictions.csv.gz",
            stored_name="predictions.csv",
        )
        serving = freezer.SNAPSHOT_DIR / "model_serving_config.json"
        freezer.freeze_serving_configuration(serving)
        destination = freezer.ANNOTATIONS_DEST
        kept = (destination / ADJUDICATIONS).read_bytes()
        shutil.rmtree(destination)
        destination.mkdir(parents=True)
        if "unnamed_wave" in defects:
            kept = base_blob(ADJUDICATIONS_PATH)
        (destination / ADJUDICATIONS).write_bytes(kept)
        for name in (ROWS, NOTES, EXPLANATIONS):
            freezer.copy_exact(freezer.SOURCE_ANNOTATIONS / name, destination / name)
        manifest = json.loads(base_blob(SNAPSHOT_DIR / "manifest.json"))
        manifest["description"] = manifest["description"].replace(
            manifest["snapshot_date"], freezer.SNAPSHOT_DATE
        )
        manifest["snapshot_date"] = freezer.SNAPSHOT_DATE
        manifest["reference_output_refresh"]["snapshot_date"] = freezer.SNAPSHOT_DATE
        if freezer.REFERENCE_PINS is not None:
            manifest["reference_output_refresh"] = freezer.read_reference_refresh()
            manifest["committed_snapshot_artifacts"]["us_reference_outputs.csv"] = (
                freezer.REFERENCE_PINS["reference_outputs.csv"]
            )
        manifest["scope"]["models"] = 46 if "models_46" in defects else 47
        manifest["model_response_date"] = window
        records = json.loads((run / EXCLUSIONS).read_text())["exclusions"]
        manifest["reference_exclusions"]["outputs"] = len(records)
        manifest["reference_exclusions"]["scored_outputs_per_model"] = 1984 - len(
            records
        )
        manifest["published_dashboard_artifact"] = freezer.PUBLISHED_DASHBOARD_ARTIFACT
        pointer = json.loads((freezer.ROOT / "app/src/data.artifact.json").read_text())
        manifest["live_dashboard_artifact"].update(
            {key: pointer[key] for key in ("tag", "asset", "url", "sha256", "bytes")}
        )
        files = manifest["source_run_artifacts"][RUN]["files"]
        if freezer.REFERENCE_PINS is not None:
            files.update(freezer.REFERENCE_PINS)
        files[EXCLUSIONS] = freezer.sha256_file(run / EXCLUSIONS)
        files["predictions.csv.gz"] = freezer.sha256_file(run / "predictions.csv.gz")
        committed = manifest["committed_snapshot_artifacts"]
        committed["model_serving_config.json"] = freezer.sha256_file(serving)
        audit = manifest["audit_annotation_artifacts"]["files"]
        for name in (ADJUDICATIONS, ROWS, NOTES):
            audit[name] = freezer.sha256_file(destination / name)
        if freezer.REFERENCE_PINS is not None:
            audit[EXPLANATIONS] = freezer.sha256_file(destination / EXPLANATIONS)
        if "outside" in defects:
            manifest["population_weight_artifact"]["sha256"] = "0" * 64
        if "pinned_reference" in defects:
            files["reference_outputs.csv"] = "0" * 64
        if "explanations_pin" in defects:
            audit[EXPLANATIONS] = "0" * 64
        if "window" in defects:
            manifest["model_response_date"] = "2026-06-12 to 2026-10-09"
        (freezer.SNAPSHOT_DIR / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )

    return main


@pytest.fixture
def frozen_board(staged_board, monkeypatch):
    """A releasable synthetic stage: release 20261006's references and the
    release's exclusion record, the ruled record as adjudicate-exclusions
    writes it, and each decided case's verdict. Gates whose inputs the
    synthetic audit cannot hold (the annotations rebuilt from release
    20261006's 77 decided cases, and the applied-adjudications check) are
    stubbed; they are tested above and in test_finish_haiku55.py. The
    freezer's own main is a stand-in (_fake_freezer_main)."""
    import pandas as pd

    import policybench.adjudications

    stage, rebind = staged_board
    pinned_references(stage / BUNDLE / "us")
    record = _stage_ruled_record(stage)
    write_judge_verdicts(stage / "audit/cases", record)
    rebind(bind=_ruled_case_files(stage))
    checked = []
    monkeypatch.setattr(
        release,
        "verify_annotation_amendments",
        lambda annotations, amendments, audit: checked.append(amendments),
    )
    monkeypatch.setattr(
        policybench.adjudications, "verify_adjudications_applied", lambda *a: None
    )
    staged_rows = pd.read_csv(stage / BUNDLE / "us/predictions.csv")
    incumbent_rows = staged_rows[staged_rows["model"] != HAIKU].reset_index(drop=True)
    monkeypatch.setattr(release, "base_prediction_rows", lambda: incumbent_rows)
    monkeypatch.setattr(
        freezer, "freeze_serving_configuration", _serving_from_the_registry
    )
    monkeypatch.setattr(freezer, "_serving_registry_commit", lambda payload: "f" * 40)
    calls, defects = [], set()
    monkeypatch.setattr(freezer, "main", _fake_freezer_main(calls, defects))
    return types.SimpleNamespace(
        stage=stage,
        rebind=rebind,
        record=record,
        calls=calls,
        defects=defects,
        checked=checked,
    )


def test_a_dry_run_of_a_releasable_stage_writes_nothing(frozen_board, capsys):
    stage = frozen_board.stage
    before = workspace_files()
    release.main(["--stage-dir", str(stage), "--dry-run"])
    assert workspace_files() == before
    assert frozen_board.calls == []
    out = capsys.readouterr().out
    assert f"Validated local release inputs: {driver.RELEASE_TAG}, 47 models" in out
    assert "74 exclusions (10 new)" in out
    assert f"model responses {WINDOW}; snapshot 2026-10-09; nothing written" in out


def _live_version(versions: dict) -> dict:
    return next(v for v in versions["versions"] if v["id"] == versions["default"])


def test_the_freeze_writes_the_release(frozen_board, capsys):
    """The pointer, the version list, the frozen run's references and
    74-record exclusion record, the annotations with the record that names
    the 2026-10-06 wave, the wording amendments record, the serving rows, and
    the release's predictions asset."""
    stage = frozen_board.stage
    payload = stage / "data-board47.json"
    release.main(["--stage-dir", str(stage)])
    assert f"Built {driver.RELEASE_TAG} locally" in capsys.readouterr().out
    root = release.ROOT
    tag = driver.RELEASE_TAG
    pointer = {
        "version": 1,
        "repo": "PolicyEngine/policybench",
        "tag": tag,
        "asset": "dashboard-data.json",
        "url": (
            "https://github.com/PolicyEngine/policybench/releases/download/"
            f"{tag}/dashboard-data.json"
        ),
        "sha256": sha(payload),
        "bytes": payload.stat().st_size,
    }
    assert (root / release.POINTER).read_text() == (
        json.dumps(pointer, indent=2, sort_keys=True) + "\n"
    )
    versions = json.loads((root / release.VERSIONS).read_text())
    previous = json.loads(base_blob(Path(release.VERSIONS)))
    live = _live_version(versions)
    assert live["snapshotLabel"] == "Snapshot 2026-10-09"
    assert live["description"].endswith(" - 47 models")
    assert (
        "the 74 excluded outputs keep the values they were decided on: 52 from "
        "policyengine-us 1.755.4, 22 from 2.15.17" in live["description"]
    )
    others = [v for v in versions["versions"] if v is not live]
    assert others == [v for v in previous["versions"] if v["id"] != previous["default"]]
    # The frozen run: release 20261006's references and the release's record.
    frozen = root / FROZEN_RUN
    assert (frozen / EXCLUSIONS).read_text() == release_exclusions_text()
    assert len(json.loads((frozen / EXCLUSIONS).read_text())["exclusions"]) == 74
    for name in release.PINNED_REFERENCES:
        assert (frozen / name).read_bytes() == base_blob(FROZEN_RUN / name)
    # The annotations: the staged record and CSVs, and the amendments record.
    annotations = root / ANNOTATIONS_DIR
    assert sorted(p.name for p in annotations.iterdir()) == sorted(
        (ADJUDICATIONS, ROWS, NOTES, EXPLANATIONS, AMENDMENTS_RECORD)
    )
    staged_annotations = stage / BUNDLE / "annotations"
    for name in (ADJUDICATIONS, ROWS, NOTES, EXPLANATIONS):
        assert (annotations / name).read_bytes() == (
            staged_annotations / name
        ).read_bytes()
    committed = json.loads((annotations / ADJUDICATIONS).read_text())
    assert committed == frozen_board.record
    conventions = committed["date_conventions"]
    assert "(2026-09-05, 2026-09-22, 2026-09-29, 2026-10-05 or 2026-10-06)" in (
        conventions
    )
    assert conventions.count(f"and were written on {WRITTEN_ON} UTC.") == 1
    from policybench.adjudications import excluded_case_keys, parse_adjudications

    entries = parse_adjudications(committed, "frozen")
    assert excluded_case_keys(entries) == {
        (r["scenario_id"], r["variable"]) for r in release_exclusions()
    }
    assert (annotations / AMENDMENTS_RECORD).read_bytes() == base_blob(
        ANNOTATIONS_DIR / AMENDMENTS_RECORD
    )
    # The serving rows: release 20261006's, and Claude Haiku 5.5's run state.
    serving = json.loads(
        (root / SNAPSHOT_DIR / "model_serving_config.json").read_text()
    )
    previous_serving = json.loads(base_blob(SNAPSHOT_DIR / "model_serving_config.json"))
    for model, row in previous_serving["models"].items():
        assert serving["models"][model] == row
    assert serving["models"][HAIKU]["evidence"] == {
        "kind": "run_state",
        "run": f"haiku55-runs/{SLUG}",
    }
    assert serving["evidence_summary"] == {
        "registry": previous_serving["evidence_summary"]["registry"],
        "run_state": previous_serving["evidence_summary"]["run_state"] + 1,
    }
    assert serving["registry_commit"] == "f" * 40
    # The freezer read the stage, as configured.
    [configured] = frozen_board.calls
    assert configured["SNAPSHOT_DATE"] == "2026-10-09"
    assert configured["SOURCE_RUN"] == stage / BUNDLE
    assert configured["SOURCE_US"] == stage / BUNDLE / "us"
    assert configured["SOURCE_ANNOTATIONS"] == staged_annotations
    assert configured["REFERENCE_META_SOURCE"] == (
        stage / BUNDLE / "us/reference_outputs.csv.meta.json"
    )
    assert configured["PUBLISHED_DASHBOARD_SOURCE"] == payload
    assert configured["PUBLISHED_DASHBOARD_ARTIFACT"] == {
        key: pointer[key] for key in ("tag", "asset", "url", "sha256", "bytes")
    }
    assert configured["RUN_STATE_EVIDENCE"] == {
        HAIKU: str(stage / "inputs" / SLUG / "run_state.json")
    }
    assert configured["AUDIT_CASES_DIR"] == stage / "audit/cases"
    assert frozen_board.checked == [[]]
    # The release assets beside the stage, and the dashboard's local cache.
    assert (stage / "predictions.csv.gz").read_bytes() == (
        frozen / "predictions.csv.gz"
    ).read_bytes()
    cache = root / "app/.cache" / f"dashboard-data-{sha(payload)[:16]}.json"
    assert cache.read_bytes() == payload.read_bytes()


def test_freezing_twice_writes_the_same_files(frozen_board):
    """A second freeze of the same stage finds this release's committed
    record and pins where release 20261006's were, passes, and writes the
    same bytes."""
    stage = frozen_board.stage
    release.main(["--stage-dir", str(stage)])
    first = workspace_files()
    release.main(["--stage-dir", str(stage)])
    assert workspace_files() == first


@pytest.mark.parametrize(
    "defect, message",
    [
        ("base_exclusions", "frozen reference reference_exclusions.json does not"),
        ("unnamed_wave", f"frozen {ADJUDICATIONS} is not the staged one"),
        ("outside", r"changes outside the release: \['population_weight_artifact"),
        ("pinned_reference", r"outside the release: \['source_run_artifacts\..*"),
        ("explanations_pin", f"outside the release.*files.{EXPLANATIONS}"),
        ("models_46", "does not state the release.*'scope.models': 46"),
        ("window", "does not state the release.*model_response_date"),
    ],
)
def test_the_freeze_refuses_what_the_freezer_wrote_outside_the_release(
    frozen_board, defect, message
):
    frozen_board.defects.add(defect)
    with pytest.raises(SystemExit, match=message):
        release.main(["--stage-dir", str(frozen_board.stage)])


def test_an_incumbent_prediction_change_is_refused_before_mutation(
    frozen_board, monkeypatch
):
    import pandas as pd

    stage = frozen_board.stage
    rows = release.base_prediction_rows().copy()
    rows.loc[rows["model"] == INCUMBENT, "prediction"] = 901.0
    monkeypatch.setattr(release, "base_prediction_rows", lambda: rows)
    assert isinstance(rows, pd.DataFrame)
    before = workspace_files()
    with pytest.raises(SystemExit, match=f"Incumbent prediction evidence.*{INCUMBENT}"):
        release.main(["--stage-dir", str(stage)])
    assert workspace_files() == before


@pytest.mark.parametrize(
    "edit",
    [
        {"completed": 99},
        {"total": 99, "completed": 99},
        {"stopped_reason": "budget"},
        {"model": "claude-haiku-5"},
        {"treatment_fingerprint": None},
    ],
)
def test_an_incomplete_run_state_is_refused_before_mutation(
    frozen_board, monkeypatch, edit
):
    """The pinned run itself incomplete, stopped, another model's or without
    its treatment, every pin and hash following it, is refused before any
    workspace mutation."""
    stage = frozen_board.stage
    inputs = stage / "inputs" / SLUG
    _edit_json(inputs / "run_state.json", lambda state: state.update(edit))
    pins = {SLUG: {name: sha(inputs / name) for name in PINNED}}
    monkeypatch.setattr(driver, "committed_input_pins", lambda: pins)
    frozen_board.rebind()
    before = workspace_files()
    with pytest.raises(SystemExit, match="Missing completed run or treatment"):
        release.main(["--stage-dir", str(stage)])
    assert workspace_files() == before


# --- What the freezer wrote ----------------------------------------------------


@pytest.mark.parametrize(
    "defect, message",
    [
        ("extra_file", "Frozen annotation files are not the release's"),
        ("unnamed_wave", "beyond naming the 2026-10-06 wave"),
        ("other_window", "does not state the release.*model_response_date"),
        ("other_date", "does not state the release.*snapshot_date"),
    ],
)
def test_verify_frozen_checks_what_the_freezer_wrote(frozen_board, defect, message):
    """After a freeze, verify_frozen refuses an annotations directory holding
    anything else, a frozen record (equal to the staged one) whose
    conventions do not name the wave, and a manifest that states another
    window or snapshot date than the freeze derived."""
    stage = frozen_board.stage
    release.main(["--stage-dir", str(stage)])
    annotations = release.ROOT / ANNOTATIONS_DIR
    window, snapshot_date = WINDOW, "2026-10-09"
    if defect == "extra_file":
        (annotations / "notes.txt").write_text("Left behind.\n")
    elif defect == "unnamed_wave":
        for path in (annotations, stage / BUNDLE / "annotations"):
            (path / ADJUDICATIONS).write_bytes(base_blob(ADJUDICATIONS_PATH))
    elif defect == "other_window":
        window = "2026-06-12 to 2026-10-09"
    else:
        snapshot_date = "2026-10-10"
    pointer = json.loads((release.ROOT / release.POINTER).read_text())
    serving = json.loads(base_blob(SNAPSHOT_DIR / "model_serving_config.json"))
    arguments = dict(
        stage=stage,
        snapshot=release.ROOT / SNAPSHOT_DIR,
        annotations=annotations,
        exclusions_sha256=hashlib.sha256(
            release_exclusions_text().encode()
        ).hexdigest(),
        pointer=pointer,
        window=window,
        snapshot_date=snapshot_date,
        previous_serving=serving,
        incumbents=set(serving["models"]),
        runs={SLUG: f"haiku55-runs/{SLUG}"},
    )
    with pytest.raises(SystemExit, match=message):
        release.verify_frozen(**arguments)


@functools.cache
def _manifest_text() -> str:
    return base_blob(SNAPSHOT_DIR / "manifest.json").decode()


def manifest_leaves(value, path=()):
    if isinstance(value, dict) and value:
        for key, item in value.items():
            yield from manifest_leaves(item, (*path, key))
    elif isinstance(value, list) and value:
        for index, item in enumerate(value):
            yield from manifest_leaves(item, (*path, index))
    else:
        yield path


@functools.cache
def _leaves() -> tuple:
    return tuple(manifest_leaves(json.loads(_manifest_text())))


def _set(value, path, new):
    for part in path[:-1]:
        value = value[part]
    value[path[-1]] = new


def _allowed(path) -> bool:
    return path not in release.MANIFEST_PINNED and any(
        path[: len(prefix)] == prefix for prefix in release.MANIFEST_CHANGES
    )


@examples(300)
@given(picks=st.sets(st.integers(min_value=0, max_value=10**6), max_size=6))
def test_the_frozen_manifest_changes_only_where_the_release_may(picks):
    """For any set of changed leaves of release 20261006's manifest, the
    problems are exactly the changed leaves outside the release's paths or at
    a pinned reference, each once."""
    leaves = _leaves()
    before = json.loads(_manifest_text())
    after = copy.deepcopy(before)
    changed = {leaves[pick % len(leaves)] for pick in picks}
    for index, path in enumerate(sorted(changed, key=repr)):
        _set(after, path, ["changed", index])
    problems = release.manifest_problems(before, after)
    assert len(problems) == len(set(problems))
    assert set(problems) == {path for path in changed if not _allowed(path)}


def test_the_manifest_paths_the_release_may_change():
    before = json.loads(_manifest_text())
    files = ("source_run_artifacts", RUN, "files")
    allowed = [
        ("scope", "models"),
        ("snapshot_date",),
        ("model_response_date",),
        ("reference_exclusions", "outputs"),
        (*files, EXCLUSIONS),
        (*files, "data.json.gz"),
        ("audit_annotation_artifacts", "files", ADJUDICATIONS),
    ]
    refused = [
        ("scope", "households"),
        ("population_weight_artifact", "sha256"),
        ("committed_snapshot_artifacts", "us_reference_outputs.csv"),
        ("source_run_artifacts", RUN, "prompt_payload_sha256"),
        *((*files, name) for name in release.PINNED_REFERENCES),
        ("audit_annotation_artifacts", "files", EXPLANATIONS),
    ]
    for path in allowed + refused:
        after = copy.deepcopy(before)
        _set(after, path, "changed")
        expected = [] if path in allowed else [path]
        assert release.manifest_problems(before, after) == expected, path
    after = copy.deepcopy(before)
    after["a_new_block"] = {}
    assert release.manifest_problems(before, after) == [("a_new_block",)]


# --- MOCK installed engine upgrades -----------------------------------------------


def _install_MOCK_build(
    stage: Path, receipt: dict, build, *, with_inherited_setup: bool = True
) -> driver.Upgrade:
    """MOCK: reproduce install-references' file and stage.json bindings.

    The synthetic audit is intentionally smaller than the committed board, so
    rendering a real install is unsuitable here. The build itself is gated
    against the real release 20261006 by load_build, without replacing it.
    """
    # MOCK values/narratives retain the inherited convention setup; the real
    # freezer still validates the sidecar's setup note before its first write.
    inherited = json.loads(base_blob(FROZEN_RUN / driver.META_NAME))["revisions"][-1]
    if with_inherited_setup:
        mock_builds.edit_json(
            build.built / driver.META_NAME,
            lambda meta: meta["revisions"][-1].update(
                fix_modules=inherited["fix_modules"], builder=inherited["builder"]
            ),
        )
    upgrade = mock_builds.load(build)
    copy_dir = stage / driver.BUILD_COPY
    copy_dir.mkdir(exist_ok=True)
    for name in driver.BUILD_COPY_FILES:
        source = {
            driver.EXPLANATIONS_NAME: build.explanations,
            driver.ACTIONS_NAME: build.actions,
        }.get(name, build.built / name)
        shutil.copyfile(source, copy_dir / name)
        receipt["files"][str(Path(driver.BUILD_COPY) / name)] = sha(copy_dir / name)
    prepared = json.loads((stage / "stage.json").read_text())
    for target in (stage / "scoring", stage / BUNDLE / "us"):
        target.mkdir(exist_ok=True)
        for name in driver.UPGRADED_FILES:
            shutil.copyfile(copy_dir / name, target / name)
    for name in ("scenarios.csv", "scenarios.csv.meta.json"):
        shutil.copyfile(stage / BUNDLE / "us" / name, stage / "scoring" / name)
    shutil.copyfile(
        copy_dir / EXPLANATIONS, stage / BUNDLE / "annotations" / EXPLANATIONS
    )
    for name in driver.UPGRADED_FILES:
        prepared["files"][str(BUNDLE / "us" / name)] = upgrade.sha256[name]
    prepared["files"][str(BUNDLE / "annotations" / EXPLANATIONS)] = upgrade.sha256[
        EXPLANATIONS
    ]
    prepared["references_installed"] = driver.references_record(upgrade, None)
    driver.bind_build_exclusions(stage, prepared, upgrade)
    record = driver.exclusion_adjudications(
        driver.base_adjudication_record(),
        stage / "audit/cases",
        upgrade.regenerated_ruled,
    )
    record, dropped = driver.drop_regenerated_adjudications(record, upgrade)
    prepared["adjudications_dropped"] = dropped
    (stage / "stage.json").write_text(json.dumps(prepared))
    (stage / BUNDLE / "annotations" / ADJUDICATIONS).write_text(
        driver.record_text(record)
    )
    rewrite_receipt(stage, receipt)
    return upgrade


@pytest.fixture
def MOCK_upgraded_board(frozen_board, exports, spec, tmp_path):
    """MOCK: a releasable upgraded board, four ruled defects and WI_042 fixed.

    It newly excludes nothing, so the spec's upgrade_adjudications (the real
    build's Indiana county decisions) and its triage decisions are left out.
    WI_042 is a committed decision whose drop must be bound and checked.
    """
    spec["regenerated_by_upgrade"] = mock_builds.upgrade_spec_dict()[
        "regenerated_by_upgrade"
    ]
    spec.pop("upgrade_adjudications", None)
    spec.pop("triage_adjudications", None)
    build = mock_builds.real_build(
        tmp_path / "MOCK-build",
        regenerated={**mock_builds.MOCK_REGENERATED_RULED, mock_builds.WI_042: 0.0},
        added={},
    )
    stage = frozen_board.stage
    receipt = json.loads((stage / "release-ready.json").read_text())
    upgrade = _install_MOCK_build(stage, receipt, build)
    records = json.loads(upgrade.exclusions_text)["exclusions"]
    payload = stage / "data-board47.json"
    board = json.loads(payload.read_text())
    for target in (board, exports["release"]):
        country = target["countries"]["us"]
        country["referenceExclusions"] = [
            {"scenarioId": r["scenario_id"], "variable": r["variable"]} for r in records
        ]
        for row in country["modelStats"]:
            row["n"] = upgrade.scored_outputs
    payload.write_text(json.dumps(board))

    def rebind():
        receipt["payload_sha256"] = sha(payload)
        rewrite_receipt(stage, receipt)

    rebind()
    frozen_board.upgrade = upgrade
    frozen_board.build = build
    frozen_board.receipt = receipt
    frozen_board.rebind = rebind
    frozen_board.record = json.loads(
        (stage / BUNDLE / "annotations" / ADJUDICATIONS).read_text()
    )
    return frozen_board


def test_MOCK_installed_upgrade_is_gated_and_accepted(MOCK_upgraded_board):
    """MOCK: retained build, installed copies and dropped decisions all agree."""
    board = MOCK_upgraded_board
    assert release.verify_upgrade(board.stage, board.receipt) == board.upgrade
    assert board.upgrade.records == 69 and board.upgrade.scored_outputs == 1915
    assert board.upgrade.regenerated_base == {mock_builds.WI_042}
    assert board.upgrade.regenerated_ruled == set(mock_builds.MOCK_REGENERATED_RULED)


@pytest.mark.parametrize("name", driver.BUILD_COPY_FILES)
def test_MOCK_export_must_bind_every_installed_build_file(MOCK_upgraded_board, name):
    """MOCK: stage.json's build pins cannot replace each export receipt entry."""
    board = MOCK_upgraded_board
    del board.receipt["files"][str(Path(driver.BUILD_COPY) / name)]
    with pytest.raises(SystemExit, match="does not bind the installed build"):
        release.verify_upgrade(board.stage, board.receipt)


@pytest.mark.parametrize("name", driver.BUILD_COPY_FILES)
def test_MOCK_export_must_bind_the_installed_build_bytes(MOCK_upgraded_board, name):
    """MOCK: an entry with another digest is not an export binding."""
    board = MOCK_upgraded_board
    board.receipt["files"][str(Path(driver.BUILD_COPY) / name)] = "0" * 64
    with pytest.raises(SystemExit, match="does not bind the installed build's bytes"):
        release.verify_upgrade(board.stage, board.receipt)


@examples(30)
@given(
    name=st.sampled_from(driver.BUILD_COPY_FILES),
    position=st.integers(min_value=0, max_value=10**6),
    delta=st.integers(min_value=1, max_value=255),
)
def test_MOCK_any_single_byte_change_in_the_installed_build_is_refused(
    MOCK_upgraded_board, name, position, delta
):
    """MOCK: every nonzero one-byte mutation breaks the retained build pin."""
    board = MOCK_upgraded_board
    path = board.stage / driver.BUILD_COPY / name
    original = path.read_bytes()
    edited = bytearray(original)
    edited[position % len(edited)] ^= delta
    path.write_bytes(edited)
    try:
        with pytest.raises(SystemExit, match="installed build's.*changed"):
            release.verify_upgrade(board.stage, board.receipt)
    finally:
        path.write_bytes(original)


@pytest.mark.parametrize(
    "field, value",
    [
        ("engine_version", "MOCK other engine"),
        ("records", 74),
        ("changed", []),
        ("regenerated_base", []),
        ("added", [["MOCK", "snap"]]),
        ("spec_sha256", "0" * 64),
        ("superseded", None),
        ("superseded", ["MOCK malformed"]),
    ],
)
def test_MOCK_installed_build_receipt_must_be_the_drivers_record(
    MOCK_upgraded_board, field, value
):
    """MOCK: a re-hashed stage.json must still describe the gated build."""
    board = MOCK_upgraded_board
    _record_installed(
        board.stage, lambda r: r["references_installed"].update({field: value})
    )
    with pytest.raises(
        SystemExit, match="installed build.*records|installed build's record"
    ):
        release.verify_upgrade(board.stage, board.receipt)


@pytest.mark.parametrize("defect", ["absent", "extra", "duplicate", "rewritten"])
def test_MOCK_dropped_decisions_must_be_exactly_the_regenerated_base_records(
    MOCK_upgraded_board, defect
):
    """MOCK: each recorded drop must be release 20261006's actual decision."""
    board = MOCK_upgraded_board

    def edit(record):
        dropped = record["adjudications_dropped"]
        if defect == "absent":
            del record["adjudications_dropped"]
        elif defect == "extra":
            dropped.append({"case_id": "us__MOCK_extra__snap", "entry": {}})
        elif defect == "duplicate":
            dropped.append(copy.deepcopy(dropped[0]))
        else:
            dropped[0]["entry"]["reasoning"] += " MOCK rewrite."

    _record_installed(board.stage, edit)
    with pytest.raises(SystemExit, match="dropped adjudications|dropped decisions"):
        release.verify_upgrade(board.stage, board.receipt)


@pytest.mark.parametrize("dry_run", [True, False])
def test_MOCK_changed_installed_build_is_refused_before_any_write(
    MOCK_upgraded_board, dry_run
):
    """MOCK: changing a retained trace is refused before workspace mutation."""
    board = MOCK_upgraded_board
    (board.stage / driver.BUILD_COPY / mock_builds.TRACES_NAME).write_text(
        "MOCK changed\n"
    )
    before = workspace_files()
    with pytest.raises(
        SystemExit, match="Staged evidence changed|installed build's.*changed"
    ):
        release.main(["--stage-dir", str(board.stage)] + ["--dry-run"] * dry_run)
    assert workspace_files() == before and board.calls == []


@pytest.mark.parametrize("target", ["scoring", "bundle", "explanations"])
def test_MOCK_installed_build_copies_must_still_match(MOCK_upgraded_board, target):
    """MOCK: scoring, publication and explanations cannot diverge from the build."""
    board = MOCK_upgraded_board
    path = {
        "scoring": board.stage / "scoring/reference_outputs.csv",
        "bundle": board.stage / BUNDLE / "us/reference_outputs.csv",
        "explanations": board.stage / BUNDLE / "annotations" / EXPLANATIONS,
    }[target]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(SystemExit, match="not the installed build's"):
        release.verify_upgrade(board.stage, board.receipt)


@pytest.mark.parametrize("name", ["scenarios.csv", "scenarios.csv.meta.json"])
@pytest.mark.parametrize("defect", ["edited", "missing"])
def test_MOCK_scoring_scenarios_stay_pinned_to_release_20261006(
    MOCK_upgraded_board, name, defect
):
    """MOCK: an upgrade never revises the stage's household draw or its sidecar."""
    board = MOCK_upgraded_board
    path = board.stage / "scoring" / name
    if defect == "missing":
        path.unlink()
    else:
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(SystemExit, match="scoring.*scenarios.*release 20261006"):
        release.verify_upgrade(board.stage, board.receipt)


@pytest.mark.parametrize(
    "defect",
    [
        "missing_bundle_field",
        "zero_conventions",
        "13_conventions",
        "unlisted_module",
        "empty_regeneration_timestamp",
    ],
)
def test_MOCK_unsupported_manifest_sidecar_is_refused_before_any_write(
    MOCK_upgraded_board, tmp_path, defect
):
    """MOCK: a gated build must also support the freezer's truthful manifest note."""
    board = MOCK_upgraded_board
    build = mock_builds.real_build(
        tmp_path / f"MOCK-{defect}",
        regenerated={**mock_builds.MOCK_REGENERATED_RULED, mock_builds.WI_042: 0.0},
        added={},
    )
    inherited = json.loads(base_blob(FROZEN_RUN / driver.META_NAME))["revisions"][-1]

    def edit(meta):
        revision = meta["revisions"][-1]
        revision.update(
            fix_modules=copy.deepcopy(inherited["fix_modules"]),
            builder=inherited["builder"],
        )
        if defect == "missing_bundle_field":
            meta["policyengine_bundles"]["us"].pop("policyengine_version")
        elif defect == "empty_regeneration_timestamp":
            meta["regenerated_at_utc"] = ""
        elif defect == "unlisted_module":
            revision["fix_modules"].append(
                {"module": "MOCK_unknown.py", "sha256": "0" * 64}
            )
        else:
            other = [
                item
                for item in revision["fix_modules"]
                if not item["module"].startswith(freezer.CONVENTION_MODULE_PREFIX)
            ]
            count = 0 if defect == "zero_conventions" else 13
            revision["fix_modules"] = other + [
                {"module": f"latest_c_MOCK_{i}.py", "sha256": "0" * 64}
                for i in range(count)
            ]

    mock_builds.edit_json(build.built / driver.META_NAME, edit)
    _install_MOCK_build(board.stage, board.receipt, build, with_inherited_setup=False)
    before = workspace_files()
    with pytest.raises(SystemExit, match="metadata|convention|fix_modules|timestamp"):
        release.main(["--stage-dir", str(board.stage)])
    assert workspace_files() == before and board.calls == []


def test_MOCK_committed_top_level_reference_change_is_refused_before_any_write(
    MOCK_upgraded_board,
):
    """MOCK: the top-level snapshot reference must also be baseline or installed."""
    board = MOCK_upgraded_board
    path = release.ROOT / SNAPSHOT_DIR / "us_reference_outputs.csv"
    path.write_bytes(path.read_bytes() + b" ")
    before = workspace_files()
    with pytest.raises(SystemExit, match="Committed us_reference_outputs.csv changed"):
        release.main(["--stage-dir", str(board.stage)])
    assert workspace_files() == before and board.calls == []


@pytest.mark.parametrize(
    "field, value",
    [
        ("source", "MOCK wrong"),
        ("engine_version", "MOCK wrong"),
        ("records", 74),
        ("spec_sha256", "0" * 64),
    ],
)
def test_MOCK_exclusion_install_receipt_must_match_the_build(
    MOCK_upgraded_board, field, value
):
    """MOCK: install-references binds the exclusion count, source and engine."""
    board = MOCK_upgraded_board
    _record_installed(
        board.stage, lambda r: r["exclusions_installed"].update({field: value})
    )
    with pytest.raises(SystemExit, match="stage.json does not record"):
        release.verify_installed_exclusions(
            board.stage, board.receipt, board.upgrade.exclusions_text, board.upgrade
        )


def test_MOCK_explanations_are_the_builds_bytes(MOCK_upgraded_board):
    """MOCK: unchanged baseline explanations fail even when their hash is rebound."""
    board = MOCK_upgraded_board
    annotations = board.stage / BUNDLE / "annotations"
    release.verify_explanations(annotations, board.upgrade, stage=board.stage)
    (annotations / EXPLANATIONS).write_bytes(base_blob(ANNOTATIONS_DIR / EXPLANATIONS))
    with pytest.raises(
        SystemExit, match=f"Staged {EXPLANATIONS}.*installed engine upgrade"
    ):
        release.verify_explanations(annotations, board.upgrade, stage=board.stage)


@pytest.mark.parametrize("defect", ["missing", "edited"])
def test_MOCK_explanation_build_must_exist_and_match_its_pin(
    MOCK_upgraded_board, defect
):
    """MOCK: inferring stage from the annotation path still checks retained bytes."""
    board = MOCK_upgraded_board
    annotations = board.stage / BUNDLE / "annotations"
    release.verify_explanations(annotations, board.upgrade)
    built = board.stage / driver.BUILD_COPY / EXPLANATIONS
    if defect == "missing":
        built.unlink()
    else:
        built.write_bytes(built.read_bytes() + b" ")
    with pytest.raises(SystemExit, match="installed build's.*changed"):
        release.verify_explanations(annotations, board.upgrade)


@pytest.mark.parametrize("defect", ["record_bytes", "receipt_pin"])
def test_MOCK_installed_exclusion_gate_checks_its_bytes_and_export_binding(
    MOCK_upgraded_board, defect
):
    """MOCK: the exclusion file is strictly the installed build's recorded bytes."""
    board = MOCK_upgraded_board
    if defect == "record_bytes":
        path = board.stage / BUNDLE / "us" / EXCLUSIONS
        path.write_bytes(path.read_bytes() + b" ")
    else:
        board.receipt["files"][str(BUNDLE / "us" / EXCLUSIONS)] = "0" * 64
    with pytest.raises(
        SystemExit, match="not the installed engine upgrade|does not bind the installed"
    ):
        release.verify_installed_exclusions(
            board.stage, board.receipt, board.upgrade.exclusions_text, board.upgrade
        )


def test_MOCK_upgrade_without_regenerated_base_records_requires_an_empty_drop_log(
    MOCK_upgraded_board, tmp_path
):
    """MOCK: no regenerated base decision still requires an explicit empty log."""
    board = MOCK_upgraded_board
    build = mock_builds.real_build(tmp_path / "MOCK-no-base-drops", added={})
    upgrade = _install_MOCK_build(board.stage, board.receipt, build)
    assert not upgrade.regenerated_base
    assert release.verify_upgrade(board.stage, board.receipt) == upgrade
    _record_installed(board.stage, lambda record: record.pop("adjudications_dropped"))
    with pytest.raises(SystemExit, match="records no dropped adjudications"):
        release.verify_upgrade(board.stage, board.receipt)


def test_MOCK_payload_counts_and_exclusion_order_follow_the_build(MOCK_upgraded_board):
    """MOCK: exactly 69 ordered exclusions leave 1,915 outputs for every model."""
    upgrade = MOCK_upgraded_board.upgrade
    records = json.loads(upgrade.exclusions_text)["exclusions"]
    country = _payload_country(records, upgrade.scored_outputs)
    release.verify_scored_outputs(country, records, upgrade)
    country["modelStats"][0]["n"] = driver.RELEASE_SCORED
    with pytest.raises(SystemExit, match="scored on 1915"):
        release.verify_scored_outputs(country, records, upgrade)
    country["modelStats"][0]["n"] = upgrade.scored_outputs
    country["referenceExclusions"].reverse()
    with pytest.raises(SystemExit, match="their order"):
        release.verify_scored_outputs(country, records, upgrade)
    with pytest.raises(SystemExit, match="exclusion record does not count"):
        release.verify_scored_outputs(
            _payload_country(records[:-1], upgrade.scored_outputs),
            records[:-1],
            upgrade,
        )


@pytest.mark.parametrize("name", driver.REFERENCE_FILES)
@pytest.mark.parametrize("location", ["stage", "committed", "manifest"])
def test_MOCK_reference_gates_keep_every_stage_committed_and_manifest_pin(
    MOCK_upgraded_board, name, location
):
    """MOCK: all five pins are checked, including unchanged scenario sidecars."""
    board = MOCK_upgraded_board
    source = board.stage / BUNDLE / "us"
    frozen = release.ROOT / FROZEN_RUN
    manifest = json.loads(base_blob(SNAPSHOT_DIR / "manifest.json"))
    pin = board.upgrade.sha256[EXCLUSIONS]
    release.verify_references(source, frozen, manifest, pin, board.upgrade)
    if location == "manifest":
        manifest["source_run_artifacts"][RUN]["files"][name] = "0" * 64
    else:
        path = (source if location == "stage" else frozen) / name
        path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(SystemExit, match=f"{name}.*changed|Manifest pin for {name}"):
        release.verify_references(source, frozen, manifest, pin, board.upgrade)


@pytest.mark.parametrize(
    "path",
    [
        ("committed_snapshot_artifacts", "us_reference_outputs.csv"),
        ("audit_annotation_artifacts", "files", EXPLANATIONS),
    ],
)
def test_MOCK_reference_gate_checks_additional_committed_and_explanation_pins(
    MOCK_upgraded_board, path
):
    """MOCK: a previous freeze's extra reference and explanation pins must match."""
    board = MOCK_upgraded_board
    manifest = json.loads(base_blob(SNAPSHOT_DIR / "manifest.json"))
    _set(manifest, path, "0" * 64)
    with pytest.raises(SystemExit, match="Manifest pin for"):
        release.verify_references(
            board.stage / BUNDLE / "us",
            release.ROOT / FROZEN_RUN,
            manifest,
            board.upgrade.sha256[EXCLUSIONS],
            board.upgrade,
        )


def test_MOCK_adjudication_gate_accepts_only_kept_ruled_and_recorded_drops(
    MOCK_upgraded_board,
):
    """MOCK: regenerated ruled cells have no decision and WI_042's is dropped."""
    board = MOCK_upgraded_board
    assert (
        release.verify_adjudication_record(
            board.stage / BUNDLE / "annotations" / ADJUDICATIONS,
            board.stage / BUNDLE / "us",
            frozenset(),
            [],
            board.stage / "audit/cases",
            board.upgrade,
        )
        == 0
    )


@pytest.mark.parametrize(
    "defect",
    ["dropped_restored", "kept_dropped", "unruled_rewritten", "extra_decision"],
)
def test_MOCK_adjudication_gate_refuses_any_other_decision_change(
    MOCK_upgraded_board, defect
):
    """MOCK: an upgrade permits only the driver's exact decisions and drops."""
    board = MOCK_upgraded_board
    path = board.stage / BUNDLE / "annotations" / ADJUDICATIONS
    record = json.loads(path.read_text())
    if defect == "dropped_restored":
        prepared = json.loads((board.stage / "stage.json").read_text())
        record["adjudications"].append(prepared["adjudications_dropped"][0]["entry"])
    elif defect == "kept_dropped":
        record["adjudications"].pop()
    elif defect == "unruled_rewritten":
        record["adjudications"][0]["reasoning"] += " MOCK extra reasoning."
    else:
        entry = copy.deepcopy(record["adjudications"][0])
        entry["scenario_id"] = "MOCK_extra"
        record["adjudications"].append(entry)
    path.write_text(driver.record_text(record))
    with pytest.raises(SystemExit):
        release.verify_adjudication_record(
            path,
            board.stage / BUNDLE / "us",
            frozenset(),
            [],
            board.stage / "audit/cases",
            board.upgrade,
        )


def test_MOCK_added_exclusions_freeze_only_as_the_spec_decides_them(
    MOCK_upgraded_board, spec, tmp_path
):
    """MOCK: an upgrade's new exclusions (the two Indiana county outputs) pass
    when the spec's upgrade_adjudications decide exactly them, and are refused
    when it decides none."""
    board = MOCK_upgraded_board
    made = mock_builds.real_build(
        tmp_path / "MOCK-added",
        regenerated={**mock_builds.MOCK_REGENERATED_RULED, mock_builds.WI_042: 0.0},
    )
    _install_MOCK_build(board.stage, board.receipt, made)
    with pytest.raises(SystemExit, match="must decide exactly"):
        release.verify_upgrade(board.stage, board.receipt)
    spec["upgrade_adjudications"] = release_spec()["upgrade_adjudications"]
    assert {driver.spec_key(i) for i in spec["upgrade_adjudications"]} == set(
        mock_builds.MOCK_NEW
    )
    upgrade = release.verify_upgrade(board.stage, board.receipt)
    assert upgrade.added == frozenset(mock_builds.MOCK_NEW)


@pytest.mark.parametrize("dry_run", [True, False])
def test_MOCK_upgraded_stage_passes_freeze(MOCK_upgraded_board, dry_run):
    """MOCK: upgraded references, narratives, counts and pins pass the freeze."""
    board = MOCK_upgraded_board
    before = workspace_files()
    release.main(["--stage-dir", str(board.stage)] + ["--dry-run"] * dry_run)
    if dry_run:
        assert workspace_files() == before and board.calls == []
    else:
        manifest = json.loads(
            (release.ROOT / SNAPSHOT_DIR / "manifest.json").read_text()
        )
        assert manifest["reference_exclusions"]["outputs"] == board.upgrade.records
        assert (
            manifest["reference_exclusions"]["scored_outputs_per_model"]
            == board.upgrade.scored_outputs
        )
        pins = driver.upgraded_reference_pins(board.upgrade)
        assert all(
            sha(release.ROOT / FROZEN_RUN / name) == pin for name, pin in pins.items()
        )
        assert (
            manifest["reference_output_refresh"]["policyengine_us_version"] == "2.37.1"
        )
        assert (
            manifest["audit_annotation_artifacts"]["files"][EXPLANATIONS]
            == board.upgrade.sha256[EXPLANATIONS]
        )


def test_MOCK_upgraded_freeze_can_run_twice_with_identical_files(MOCK_upgraded_board):
    """MOCK: a repeated freeze accepts the installed build's committed pins."""
    release.main(["--stage-dir", str(MOCK_upgraded_board.stage)])
    before = workspace_files()
    release.main(["--stage-dir", str(MOCK_upgraded_board.stage)])
    assert workspace_files() == before


@pytest.mark.parametrize(
    "defect",
    [
        "csv_bytes",
        "top_csv_bytes",
        "meta_bytes",
        "exclusions_bytes",
        "explanations_bytes",
        "scenario_bytes",
        "csv_pin",
        "meta_pin",
        "explanations_pin",
        "committed_csv_pin",
        "exclusions_pin",
        "exclusion_count",
        "scored_count",
        "refresh_engine",
        "refresh_date",
        "refresh_csv_pin",
        "unlisted_manifest",
        *[
            f"refresh:{field}"
            for field in (
                "regenerated_at_utc",
                "policyengine_version",
                "policyengine_us_data_build_id",
                "policyengine_us_dataset",
                "policyengine_us_dataset_uri",
                "policyengine_us_data_artifact_sha256",
            )
        ],
    ],
)
def test_MOCK_verify_frozen_refuses_incorrect_build_files_pins_and_counts(
    MOCK_upgraded_board, defect
):
    """MOCK: allowed manifest changes must still state the exact installed build."""
    board = MOCK_upgraded_board
    release.main(["--stage-dir", str(board.stage)])
    snapshot = release.ROOT / SNAPSHOT_DIR
    annotations = release.ROOT / ANNOTATIONS_DIR
    files = ("source_run_artifacts", RUN, "files")
    paths = {
        "csv_pin": (*files, "reference_outputs.csv"),
        "meta_pin": (*files, "reference_outputs.csv.meta.json"),
        "explanations_pin": ("audit_annotation_artifacts", "files", EXPLANATIONS),
        "committed_csv_pin": (
            "committed_snapshot_artifacts",
            "us_reference_outputs.csv",
        ),
        "exclusions_pin": (*files, EXCLUSIONS),
        "exclusion_count": ("reference_exclusions", "outputs"),
        "scored_count": ("reference_exclusions", "scored_outputs_per_model"),
        "refresh_engine": ("reference_output_refresh", "policyengine_us_version"),
        "refresh_date": ("reference_output_refresh", "date"),
        "refresh_csv_pin": ("reference_output_refresh", "reference_csv_sha256"),
        "unlisted_manifest": ("population_weight_artifact", "sha256"),
        **{
            f"refresh:{field}": ("reference_output_refresh", field)
            for field in (
                "regenerated_at_utc",
                "policyengine_version",
                "policyengine_us_data_build_id",
                "policyengine_us_dataset",
                "policyengine_us_dataset_uri",
                "policyengine_us_data_artifact_sha256",
            )
        },
    }
    byte_paths = {
        "csv_bytes": snapshot / "runs" / RUN / "reference_outputs.csv",
        "top_csv_bytes": snapshot / "us_reference_outputs.csv",
        "meta_bytes": snapshot / "runs" / RUN / "reference_outputs.csv.meta.json",
        "exclusions_bytes": snapshot / "runs" / RUN / EXCLUSIONS,
        "explanations_bytes": annotations / EXPLANATIONS,
        "scenario_bytes": snapshot / "runs" / RUN / "scenarios.csv",
    }
    if defect in byte_paths:
        path = byte_paths[defect]
        path.write_bytes(path.read_bytes() + b" ")
    else:
        _edit_json(
            snapshot / "manifest.json", lambda m: _set(m, paths[defect], "MOCK wrong")
        )
    serving = base_serving()
    with pytest.raises(SystemExit):
        release.verify_frozen(
            stage=board.stage,
            snapshot=snapshot,
            annotations=annotations,
            exclusions_sha256=board.upgrade.sha256[EXCLUSIONS],
            pointer=json.loads((release.ROOT / release.POINTER).read_text()),
            window=WINDOW,
            snapshot_date="2026-10-09",
            previous_serving=serving,
            incumbents=set(serving["models"]),
            runs=RUNS,
            upgrade=board.upgrade,
        )


def test_MOCK_upgrade_manifest_permissions_name_only_the_new_paths(MOCK_upgraded_board):
    """MOCK: explicitly allowed upgrade leaves move; every other leaf stays pinned."""
    upgrade = MOCK_upgraded_board.upgrade
    before = json.loads(_manifest_text())
    allowed = set(release.UPGRADE_MANIFEST_CHANGES) | set(
        release.UPGRADE_MANIFEST_UNPINNED
    )
    for path in _leaves():
        after = copy.deepcopy(before)
        _set(after, path, "MOCK changed")
        expected = [] if _allowed(path) or path in allowed else [path]
        assert release.manifest_problems(before, after, upgrade) == expected, path
    after = copy.deepcopy(before)
    after["reference_output_refresh"]["MOCK_unlisted"] = "MOCK"
    assert release.manifest_problems(before, after, upgrade) == [
        ("reference_output_refresh", "MOCK_unlisted")
    ]


def test_MOCK_versions_count_records_on_the_build_engine(MOCK_upgraded_board, tmp_path):
    """MOCK: a new engine's retained records appear in the description's counts."""
    made = mock_builds.real_build(
        tmp_path / "MOCK-engine-count",
        regenerated={**mock_builds.MOCK_REGENERATED_RULED, mock_builds.WI_042: 0.0},
    )
    upgrade = mock_builds.load(made)
    records = json.loads(upgrade.exclusions_text)["exclusions"]
    versions = release.release_versions(head_versions(), records, "2026-10-09", upgrade)
    description = _live_version(versions)["description"]
    assert description.startswith(
        f"Scored reference outputs from {upgrade.engine_version} ("
    )
    assert "2 from 2.37.1" in description
    assert "were re-reviewed" not in description
    assert (
        release.release_versions(versions, records, "2026-10-09", upgrade) == versions
    )
    records[-1] = {**records[-1], "engine_version": "MOCK unsupported engine"}
    with pytest.raises(SystemExit, match="counts exclusions decided on"):
        release.release_versions(head_versions(), records, "2026-10-09", upgrade)


def _MOCK_description_upgrade() -> driver.Upgrade:
    """MOCK: minimal upgrade data solely for the version description formatter."""
    return driver.Upgrade(
        engine_version=mock_builds.MOCK_ENGINE,
        previous_engine_version=driver.BASE_ENGINE,
        revision={"excluded_outputs_rechecked": []},
        changed={},
        regenerated_base=frozenset(),
        regenerated_ruled=frozenset(),
        added=frozenset(),
        records=driver.RELEASE_EXCLUSIONS,
        exclusions_text=release_exclusions_text(),
        sha256={},
    )


@pytest.fixture
def MOCK_refresh_sidecar(tmp_path):
    """MOCK: a retained sidecar for timestamp validation alone, without an audit."""
    stage = tmp_path / "MOCK-stage"
    retained = stage / driver.BUILD_COPY
    retained.mkdir(parents=True)
    meta = json.loads(base_blob(FROZEN_RUN / driver.META_NAME))
    meta["policyengine_bundles"]["us"]["model_version"] = "2.37.1"
    path = retained / driver.META_NAME
    upgrade = replace(_MOCK_description_upgrade(), sha256={driver.CSV_NAME: "f" * 64})
    return types.SimpleNamespace(stage=stage, path=path, meta=meta, upgrade=upgrade)


@pytest.mark.parametrize(
    "defect, timestamp",
    [
        ("missing", None),
        ("none", None),
        ("integer", 20261009),
        ("boolean", True),
        ("empty", ""),
        ("whitespace", " "),
        ("date_only", "2026-10-09"),
        ("naive", "2026-10-09T18:00:00"),
        ("non_utc", "2026-10-09T18:00:00+01:00"),
        ("invalid_date", "2026-10-32T18:00:00+00:00"),
        ("invalid", "MOCK bad timestamp"),
        ("compact_date", "20261009T18:00:00Z"),
    ],
)
def test_MOCK_refresh_timestamp_refuses_missing_or_non_UTC_ISO_values(
    MOCK_refresh_sidecar, defect, timestamp
):
    """MOCK: malformed timestamps cannot determine a frozen regeneration date."""
    sidecar = MOCK_refresh_sidecar
    if defect == "missing":
        sidecar.meta.pop("regenerated_at_utc", None)
    else:
        sidecar.meta["regenerated_at_utc"] = timestamp
    sidecar.path.write_text(json.dumps(sidecar.meta))
    with pytest.raises(SystemExit, match="nonempty ISO timestamp in UTC"):
        release.upgraded_reference_refresh(sidecar.stage, sidecar.upgrade)


@pytest.mark.parametrize(
    "timestamp", ["2026-10-09T18:00:00Z", "2026-10-09T18:00:00+00:00"]
)
def test_MOCK_refresh_timestamp_preserves_valid_UTC_spellings(
    MOCK_refresh_sidecar, timestamp
):
    """MOCK: both explicit UTC offsets remain byte-for-byte as the sidecar states."""
    sidecar = MOCK_refresh_sidecar
    sidecar.meta["regenerated_at_utc"] = timestamp
    sidecar.path.write_text(json.dumps(sidecar.meta))
    refresh = release.upgraded_reference_refresh(sidecar.stage, sidecar.upgrade)
    assert refresh["date"] == "2026-10-09"
    assert refresh["regenerated_at_utc"] == timestamp
    assert refresh["reference_csv_sha256"] == sidecar.upgrade.sha256[driver.CSV_NAME]


@examples(25)
@given(count=st.integers(min_value=0, max_value=74))
def test_MOCK_version_rechecks_count_and_engine_are_truthful_and_idempotent(count):
    """MOCK: every recheck count updates the clause and keeps repeated output exact."""
    upgrade = _MOCK_description_upgrade()
    upgrade = replace(
        upgrade,
        revision={"excluded_outputs_rechecked": [{"MOCK": i} for i in range(count)]},
    )
    versions = release.release_versions(
        head_versions(), release_exclusions(), "2026-10-09", upgrade
    )
    description = _live_version(versions)["description"]
    assert description.startswith(
        f"Scored reference outputs from {upgrade.engine_version} ("
    )
    assert "move on 2.15.17 were re-reviewed" not in description
    if count:
        assert (
            f"and the {count} that move on 2.37.1 were re-reviewed and stay excluded"
            in description
        )
    else:
        assert "were re-reviewed" not in description
    assert (
        release.release_versions(versions, release_exclusions(), "2026-10-09", upgrade)
        == versions
    )


def test_MOCK_omitted_recheck_list_has_the_same_description_as_zero_rechecks():
    """MOCK: the driver permits an omitted empty recheck claim in the sidecar."""
    upgrade = _MOCK_description_upgrade()
    records = release_exclusions()
    expected = release.release_versions(head_versions(), records, "2026-10-09", upgrade)
    omitted = replace(upgrade, revision={})
    assert (
        release.release_versions(head_versions(), records, "2026-10-09", omitted)
        == expected
    )


@pytest.mark.parametrize(
    "prefix",
    [
        "MOCK reference outputs from",
        "Scored reference outputs from policyengine-us 9.9",
    ],
)
def test_MOCK_versions_refuse_an_unexpected_scored_reference_prefix(prefix):
    """MOCK: an unrelated engine description cannot be silently rewritten."""
    versions = head_versions()
    live = _live_version(versions)
    live["description"] = live["description"].replace(
        "Scored reference outputs from policyengine-us 2.15.17", prefix, 1
    )
    with pytest.raises(SystemExit, match="unexpected reference engine"):
        release.release_versions(
            versions, release_exclusions(), "2026-10-09", _MOCK_description_upgrade()
        )


@pytest.mark.parametrize(
    "defect", ["missing_anchor", "unknown_engine", "malformed_clause"]
)
def test_MOCK_versions_refuse_an_unexpected_recheck_description_shape(defect):
    """MOCK: an unrecognized re-review clause must never survive into a release."""
    versions = head_versions()
    live = _live_version(versions)
    old, new = {
        "missing_anchor": ("); same household facts", "); MOCK different facts"),
        "unknown_engine": (
            "move on 2.15.17 were re-reviewed",
            "move on 9.9 were re-reviewed",
        ),
        "malformed_clause": (
            "were re-reviewed and stay excluded",
            "MOCK unreviewed and stay excluded",
        ),
    }[defect]
    live["description"] = live["description"].replace(old, new, 1)
    with pytest.raises(SystemExit, match="unexpected re-review shape"):
        release.release_versions(
            versions, release_exclusions(), "2026-10-09", _MOCK_description_upgrade()
        )


@examples(5)
@given(
    day=st.dates(
        min_value=datetime.date(2026, 1, 1), max_value=datetime.date(2030, 12, 31)
    )
)
def test_without_an_upgrade_optional_arguments_preserve_existing_freeze_behavior(
    frozen_board, spec, day
):
    """Absent and explicit None upgrades freeze identical files for any date."""
    board = frozen_board
    assert (
        release.verify_upgrade(
            board.stage, json.loads((board.stage / "release-ready.json").read_text())
        )
        is None
    )
    records = release_exclusions()
    country = _payload_country(records)
    assert release.verify_scored_outputs(
        country, records
    ) == release.verify_scored_outputs(country, records, None)
    assert release.release_versions(
        head_versions(), records, day.isoformat()
    ) == release.release_versions(head_versions(), records, day.isoformat(), None)
    before = json.loads(_manifest_text())
    assert release.manifest_problems(before, before) == release.manifest_problems(
        before, before, None
    )
    spec["snapshot_date"] = day.isoformat()

    def published_files():
        relative = board.stage.relative_to(release.ROOT)
        return {
            path: blob
            for path, blob in workspace_files().items()
            if not path.is_relative_to(relative)
        }

    _record_installed(
        board.stage, lambda record: record.pop("references_installed", None)
    )
    board.rebind(restamp_stage=False)
    release.main(["--stage-dir", str(board.stage)])
    absent = published_files()
    _record_installed(
        board.stage, lambda record: record.update(references_installed=None)
    )
    board.rebind(restamp_stage=False)
    release.main(["--stage-dir", str(board.stage)])
    assert published_files() == absent


@pytest.mark.parametrize(
    "stage",
    [
        Path(
            "/Users/maxghenis/PolicyEngine/policybench-wt/release-haiku55/results/local/release-haiku55/stage"
        ),
        REPO / "results/local/upgrade-scratch/install-references",
    ],
)
def test_optional_live_stage_upgrade_bindings_are_read_only(stage):
    """Read-only optional stages, including the MOCK install-references rehearsal."""
    path = stage / "stage.json"
    if not path.is_file():
        pytest.skip("no live stage in this checkout")
    before = {p: p.read_bytes() for p in stage.rglob("*") if p.is_file()}
    prepared = json.loads(path.read_text())
    if prepared.get("references_installed"):
        driver.verify_installed_references(stage, prepared)
    else:
        assert driver.stage_upgrade(stage) is None
    assert {p: p.read_bytes() for p in stage.rglob("*") if p.is_file()} == before


# --- The version list --------------------------------------------------------------


def head_versions() -> dict:
    return json.loads(base_blob(Path(release.VERSIONS)))


def test_the_version_description_counts_the_releases_exclusions():
    versions = head_versions()
    out = release.release_versions(versions, release_exclusions(), "2026-10-09")
    live, before = _live_version(out), _live_version(versions)
    assert live["description"] == (
        before["description"]
        .replace("the 64 excluded outputs", "the 74 excluded outputs")
        .replace("12 from 2.15.17", "22 from 2.15.17")
        .replace(" - 46 models", " - 47 models")
    )
    assert live["snapshotLabel"] == "Snapshot 2026-10-09"
    assert {
        k: v for k, v in live.items() if k not in ("description", "snapshotLabel")
    } == {k: v for k, v in before.items() if k not in ("description", "snapshotLabel")}


@examples(100)
@given(
    day=st.dates(
        min_value=datetime.date(2026, 1, 1), max_value=datetime.date(2030, 12, 31)
    ),
    drop=st.integers(min_value=0, max_value=73),
)
def test_release_versions_changes_nothing_when_applied_twice(day, drop):
    """For any snapshot date and any record of both engines, the second
    application changes nothing, and only the live version's description and
    label differ from the input."""
    records = release_exclusions()
    records = records[:drop] + records[drop + 1 :]
    versions = head_versions()
    once = release.release_versions(versions, records, day.isoformat())
    assert release.release_versions(once, records, day.isoformat()) == once
    assert versions == head_versions()
    for got, had in zip(once["versions"], versions["versions"], strict=True):
        if had["id"] == versions["default"]:
            assert got["snapshotLabel"] == f"Snapshot {day.isoformat()}"
            assert got["description"].endswith(" - 47 models")
            assert f"the {len(records)} excluded outputs" in got["description"]
            got = {**got, "description": None, "snapshotLabel": None}
            had = {**had, "description": None, "snapshotLabel": None}
        assert got == had


@pytest.mark.parametrize("defect", ["default", "pointer", "engine", "shape"])
def test_release_versions_refuses_an_unexpected_version_list(defect):
    versions = head_versions()
    records = release_exclusions()
    live = _live_version(versions)
    message = "The default version is not the one live-pointer version"
    if defect == "default":
        versions["default"] = "9.9"
    elif defect == "pointer":
        live["artifact"] = {"tag": "dashboard-data-20261006"}
    elif defect == "engine":
        records = [*records, {**records[0], "engine_version": "policyengine-us 3"}]
        message = "counts exclusions decided on"
    else:
        live["description"] = live["description"].replace(" - 46 models", "")
        message = "unexpected model-count shape"
    with pytest.raises(SystemExit, match=message):
        release.release_versions(versions, records, "2026-10-09")


def test_the_pointer_names_the_release_asset(tmp_path):
    payload = tmp_path / "data-board47.json"
    payload.write_text('{"countries": {}}')
    tag = driver.RELEASE_TAG
    pointer = release.release_pointer(tag, payload, "a" * 64)
    assert pointer == {
        "version": 1,
        "repo": "PolicyEngine/policybench",
        "tag": tag,
        "asset": "dashboard-data.json",
        "url": (
            "https://github.com/PolicyEngine/policybench/releases/download/"
            f"{tag}/dashboard-data.json"
        ),
        "sha256": "a" * 64,
        "bytes": len('{"countries": {}}'),
    }


# --- Serving -----------------------------------------------------------------------


def base_serving() -> dict:
    return json.loads(base_blob(SNAPSHOT_DIR / "model_serving_config.json"))


RUNS = {SLUG: f"haiku55-runs/{SLUG}"}


def _freezers_serving(tmp_path) -> dict:
    path = tmp_path / "serving.json"
    _serving_from_the_registry(path)
    return json.loads(path.read_text())


def test_merge_serving_keeps_each_incumbent_row_and_names_the_run(tmp_path):
    previous = base_serving()
    incumbents = set(previous["models"])
    merged = release.merge_serving(
        _freezers_serving(tmp_path), previous, incumbents, RUNS
    )
    assert release.serving_problems(merged, previous, incumbents, RUNS) == []
    assert {m: merged["models"][m] for m in incumbents} == previous["models"]
    assert merged["models"][HAIKU]["evidence"]["run"] == RUNS[SLUG]


@examples(100)
@given(
    pick=st.integers(min_value=0, max_value=45),
    field=st.sampled_from(["request_timeout_seconds", "evidence", "x_new"]),
    value=JSON_VALUES,
)
def test_an_incumbent_serving_row_that_changes_is_refused(tmp_path, pick, field, value):
    """Whatever the freezer wrote for an incumbent, the merge restores release
    20261006's row; and any change to a merged incumbent row is reported."""
    previous = base_serving()
    incumbents = set(previous["models"])
    model = sorted(incumbents)[pick]
    serving = _freezers_serving(tmp_path)
    serving["models"][model][field] = value
    merged = release.merge_serving(serving, previous, incumbents, RUNS)
    assert merged["models"][model] == previous["models"][model]
    edited = copy.deepcopy(merged)
    edited["models"][model] = {**merged["models"][model], "x_edit": [value]}
    problems = release.serving_problems(edited, previous, incumbents, RUNS)
    assert problems == [f"{model} is not release 20261006's row"]


@pytest.mark.parametrize("defect", ["registry", "other_run", "summary", "roster"])
def test_the_new_rows_serving_evidence_must_name_its_run(tmp_path, defect):
    previous = base_serving()
    incumbents = set(previous["models"])
    merged = release.merge_serving(
        _freezers_serving(tmp_path), previous, incumbents, RUNS
    )
    if defect == "registry":
        merged["models"][HAIKU]["evidence"] = {"kind": "registry"}
        message = "has no run-state evidence"
    elif defect == "other_run":
        merged["models"][HAIKU]["evidence"]["run"] = "adds202609/haiku55"
        message = "evidence names run 'adds202609/haiku55'"
    elif defect == "summary":
        merged["evidence_summary"]["run_state"] += 1
        message = "is not the rows' tally"
    else:
        del merged["models"][INCUMBENT]
        message = "roster differs"
    problems = release.serving_problems(merged, previous, incumbents, RUNS)
    assert any(message in problem for problem in problems), problems
    with pytest.raises(SystemExit, match="Missing frozen run-state evidence"):
        serving = _freezers_serving(tmp_path)
        serving["models"][HAIKU]["evidence"] = {"kind": "registry"}
        release.merge_serving(serving, previous, incumbents, RUNS)


def test_the_new_models_evidence_names_the_pinned_run():
    assert release.evidence_runs() == RUNS


@pytest.mark.parametrize(
    "run", [None, "haiku55/run", "haiku55-runs/haiku/run", "a/haiku55/run/x"]
)
def test_evidence_runs_refuses_pins_that_name_no_supervised_run(monkeypatch, run):
    record = {"inputs": {SLUG: {"run": run}}}
    monkeypatch.setattr(driver, "head_blob", lambda path: json.dumps(record).encode())
    with pytest.raises(SystemExit, match="does not name the supervised run"):
        release.evidence_runs()


def test_the_freeze_reads_20261006_predictions_and_serving_from_git(monkeypatch):
    import gzip

    blobs = {}

    def blob(path):
        blobs[str(path)] = True
        if path.name == "predictions.csv.gz":
            return gzip.compress(b"model,scenario_id,variable,prediction\nm,s,v,1\n")
        return json.dumps({"models": {"m": {}}}).encode()

    monkeypatch.setattr(driver, "base_commit_blob", blob)
    assert list(release.base_prediction_rows().model) == ["m"]
    assert release.base_serving_config() == {"models": {"m": {}}}
    assert blobs == {
        f"paper/snapshot/20260501/runs/{RUN}/predictions.csv.gz": True,
        "paper/snapshot/20260501/model_serving_config.json": True,
    }


# --- The freezer's destinations ------------------------------------------------


def test_the_freezer_must_write_into_this_checkout(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    point_freeze_at(workspace, monkeypatch)
    release.verify_freezer_destinations(freezer)
    monkeypatch.setattr(freezer, "RUN_DEST", tmp_path / "elsewhere")
    with pytest.raises(SystemExit, match="would write outside this checkout"):
        release.verify_freezer_destinations(freezer)
    monkeypatch.setattr(freezer, "RUN_DEST", workspace / FROZEN_RUN)
    monkeypatch.setattr(freezer, "RUN_LABEL", "another_run")
    with pytest.raises(SystemExit, match="another_run"):
        release.verify_freezer_destinations(freezer)


def test_the_freezer_is_this_checkouts():
    release.verify_freezer_destinations(freezer)


def test_the_stage_must_be_inside_this_checkout(tmp_path, monkeypatch):
    point_freeze_at(tmp_path / "workspace", monkeypatch)
    with pytest.raises(SystemExit):
        release.main(["--stage-dir", str(tmp_path / "stage"), "--dry-run"])


# --- References --------------------------------------------------------------------


@pytest.fixture
def references(tmp_path):
    """The staged references (the release's exclusion record), the committed
    copies and the manifest release 20261006 committed, from git."""
    staged = pinned_references(tmp_path / "staged")
    frozen = base_references(tmp_path / "frozen")
    manifest = json.loads(base_blob(SNAPSHOT_DIR / "manifest.json"))
    return staged, frozen, manifest, sha(staged / EXCLUSIONS)


def test_unchanged_references_pass(references):
    release.verify_references(*references)


def test_a_second_freeze_finds_this_releases_exclusion_record(references):
    staged, frozen, manifest, exclusions = references
    shutil.copyfile(staged / EXCLUSIONS, frozen / EXCLUSIONS)
    manifest["source_run_artifacts"][RUN]["files"][EXCLUSIONS] = exclusions
    release.verify_references(staged, frozen, manifest, exclusions)


@pytest.mark.parametrize("name", release.PINNED_REFERENCES)
@pytest.mark.parametrize("where", ["Staged", "Committed", "Manifest pin"])
def test_any_reference_value_revision_is_refused(references, name, where):
    staged, frozen, manifest, exclusions = references
    if where == "Staged":
        (staged / name).write_bytes((staged / name).read_bytes() + b"\n")
    elif where == "Committed":
        (frozen / name).write_bytes((frozen / name).read_bytes() + b"\n")
    else:
        manifest["source_run_artifacts"][RUN]["files"][name] = "0" * 64
    with pytest.raises(SystemExit, match=f"{where} (for )?{name}"):
        release.verify_references(staged, frozen, manifest, exclusions)


@pytest.mark.parametrize("where", ["Staged", "Committed", "Manifest pin"])
def test_the_exclusion_record_is_release_20261006s_or_this_releases(references, where):
    staged, frozen, manifest, exclusions = references
    edited = release_exclusions_text().replace('"decided_by"', '"decided_by" ', 1)
    if where == "Staged":
        # Release 20261006's record staged: install-exclusions did not run.
        (staged / EXCLUSIONS).write_bytes(base_blob(FROZEN_RUN / EXCLUSIONS))
        message = "Staged reference_exclusions.json changed: it is not the release"
    elif where == "Committed":
        (frozen / EXCLUSIONS).write_text(edited)
        message = "Committed reference_exclusions.json changed: it is neither"
    else:
        manifest["source_run_artifacts"][RUN]["files"][EXCLUSIONS] = "0" * 64
        message = "Manifest pin for reference_exclusions.json is neither"
    with pytest.raises(SystemExit, match=message):
        release.verify_references(staged, frozen, manifest, exclusions)


def test_the_staged_explanations_must_be_release_20261006s(tmp_path):
    annotations = tmp_path / "annotations"
    annotations.mkdir()
    path = annotations / EXPLANATIONS
    path.write_bytes(base_blob(ANNOTATIONS_DIR / EXPLANATIONS))
    release.verify_explanations(annotations)
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(SystemExit, match="rewords no reference explanation"):
        release.verify_explanations(annotations)
    path.unlink()
    with pytest.raises(SystemExit, match="rewords no reference explanation"):
        release.verify_explanations(annotations)


# --- Adjudications -------------------------------------------------------------------


@pytest.fixture
def ruled(tmp_path):
    """The record adjudicate-exclusions writes on release 20261006's (from git
    at BASE_COMMIT), its new ruled cases' bound verdicts, and the release's
    references: the baseline every staged record is checked against."""
    cases = tmp_path / "cases"
    write_ruled_verdicts(cases)
    record = ruled_record(cases)
    staged = tmp_path / ADJUDICATIONS
    staged.write_text(driver.record_text(record))
    source_us = pinned_references(tmp_path / "us")
    return types.SimpleNamespace(
        staged=staged, record=record, cases=cases, source_us=source_us
    )


def _write(path, record):
    path.write_text(driver.record_text(record))


def _case(entry):
    return f"{entry['country']}__{entry['scenario_id']}__{entry['variable']}"


def _ruled_cases() -> set[str]:
    return {
        case_dir_name(*driver.spec_key(item))
        for item in release_spec()["adjudications"]
    }


def _unruled(record: dict) -> list[dict]:
    return [e for e in record["adjudications"] if _case(e) not in _ruled_cases()]


def _verify(ruled, rejudged=frozenset(), amendments=()):
    return release.verify_adjudication_record(
        ruled.staged,
        ruled.source_us,
        frozenset(rejudged),
        list(amendments),
        ruled.cases,
    )


def test_the_ruled_record_passes_the_record_gate(ruled):
    assert _verify(ruled) == 0
    from policybench.adjudications import excluded_case_keys, load_adjudications

    assert len(excluded_case_keys(load_adjudications(ruled.staged))) == 74


def test_release_20261006s_record_is_refused_until_the_wave_is_named(ruled):
    ruled.staged.write_bytes(base_blob(ADJUDICATIONS_PATH))
    with pytest.raises(SystemExit, match="beyond naming the 2026-10-06 wave"):
        _verify(ruled)


def test_the_record_must_exclude_what_the_staged_record_lists(ruled):
    """With release 20261006's exclusion record staged, the ten ruled
    decisions exclude outputs the record does not."""
    pinned_references(
        ruled.source_us, exclusions=base_blob(FROZEN_RUN / EXCLUSIONS).decode()
    )
    with pytest.raises(SystemExit, match="disagree on the excluded outputs"):
        _verify(ruled)


def test_triage_may_add_a_decision_that_keeps_the_output_scored(ruled):
    record = ruled.record
    scored = next(
        e
        for e in _unruled(record)
        if not e.get("excluded_from_scoring") and e["judge_model"] == driver.JUDGE_MODEL
    )
    added = {**copy.deepcopy(scored), "scenario_id": "scenario_999"}
    record["adjudications"].append(added)
    _write(ruled.staged, record)
    # A new decision names the case's current bound Opus 5.5 verdict.
    with pytest.raises(SystemExit, match="not restated by the restate script"):
        _verify(ruled, rejudged={_case(added)})
    _bind_current_verdict(ruled.cases, added)
    assert _verify(ruled, rejudged={_case(added)}) == 1
    # A decision on a case Claude Haiku 5.5 did not re-open has no reason to
    # appear.
    with pytest.raises(SystemExit, match="did not re-open"):
        _verify(ruled)


def _restated(entry, day="2026-10-08"):
    from restate_gpt61sol_adjudications import named_item

    return {
        **entry,
        "judge_failure_subtype": "thresholds_rates",
        "judge_rejudged_on": day,
        "judge_previous": [*entry.get("judge_previous", []), named_item(entry)],
        **({"judged_on_utc": day} if "judged_on_utc" in entry else {}),
    }


def _bind_current_verdict(cases: Path, entry: dict) -> None:
    case = cases / _case(entry)
    case.mkdir(parents=True, exist_ok=True)
    verdict = case / "verdict.json"
    verdict.write_text('{"case_failure_source": "llm_error"}')
    (case / "verdict.meta.json").write_text(
        json.dumps(
            {
                "verdict_sha256": sha(verdict),
                "judge_model_requested": driver.JUDGE_MODEL,
                "judge_model_reported": [driver.JUDGE_MODEL],
                "judged_at_utc": "2026-10-08T05:10:00+00:00",
            }
        )
    )


def test_a_rejudged_case_may_be_restated(ruled):
    record = ruled.record
    entry = next(e for e in _unruled(record) if e["judge_model"] == driver.JUDGE_MODEL)
    index = record["adjudications"].index(entry)
    record["adjudications"][index] = _restated(entry)
    _bind_current_verdict(ruled.cases, entry)
    _write(ruled.staged, record)
    assert _verify(ruled, rejudged={_case(entry)}) == 0
    # Not re-opened, the same restatement is a rewrite.
    with pytest.raises(SystemExit, match="change recorded decisions"):
        _verify(ruled)


@pytest.mark.parametrize(
    "edit",
    ["judge_class", "decision_class", "reasoning", "decision_order", "entry_order"],
)
def test_a_rewrite_of_an_incumbent_only_case_is_refused(ruled, edit):
    """No field of a case Claude Haiku 5.5 did not re-open may change, key
    order and entry order included; a re-opened case may change its judge
    fields only."""
    record = ruled.record
    entries = record["adjudications"]
    first, second = _unruled(record)[:2]
    i, j = entries.index(first), entries.index(second)
    rejudged = set()
    if edit == "judge_class":
        first["judge_failure_subtype"] = "thresholds_rates"
    elif edit == "decision_class":
        first["adjudicated_failure_subtype"] = "other"
        rejudged = {_case(first)}
    elif edit == "reasoning":
        first["reasoning"] += " Restated."
        rejudged = {_case(first)}
    elif edit == "decision_order":
        entries[i] = dict(reversed(list(first.items())))
        rejudged = {_case(first)}
    else:
        entries[i], entries[j] = entries[j], entries[i]
    _write(ruled.staged, record)
    with pytest.raises(SystemExit, match="change recorded decisions|entry order"):
        _verify(ruled, rejudged=rejudged)


def test_a_dropped_decision_is_refused(ruled):
    record = ruled.record
    record["adjudications"].remove(_unruled(record)[-1])
    _write(ruled.staged, record)
    with pytest.raises(SystemExit, match="drop recorded decisions"):
        _verify(ruled)


def test_a_new_exclusion_is_refused(ruled):
    record = ruled.record
    excluded = next(e for e in _unruled(record) if e.get("excluded_from_scoring"))
    added = {
        **copy.deepcopy(excluded),
        "scenario_id": "scenario_999",
        "judge_model": driver.JUDGE_MODEL,
    }
    record["adjudications"].append(added)
    _write(ruled.staged, record)
    _bind_current_verdict(ruled.cases, added)
    with pytest.raises(SystemExit, match="disagree on the excluded outputs"):
        _verify(ruled, rejudged={_case(added)})


@pytest.mark.parametrize(
    "edit", ["reasoning", "subtype", "judge_flag", "field_order", "restated_051"]
)
def test_a_ruled_entry_edited_by_hand_is_refused(ruled, edit):
    """Each of the ten decisions must be exactly what adjudicate-exclusions
    writes from the spec, its record and its case's bound verdict."""
    record = ruled.record
    by_case = {_case(e): e for e in record["adjudications"]}
    new = by_case[case_dir_name(*ruled_new_outputs()[0])]
    restated = by_case["us__scenario_051__state_income_tax_before_refundable_credits"]
    if edit == "reasoning":
        new["reasoning"] += " Also."
    elif edit == "subtype":
        new["adjudicated_failure_subtype"] = "other"
    elif edit == "judge_flag":
        new["judge_reference_suspect"] = not new["judge_reference_suspect"]
    elif edit == "field_order":
        index = record["adjudications"].index(new)
        items = list(new.items())
        items[6], items[7] = items[7], items[6]
        record["adjudications"][index] = dict(items)
    else:
        restated["reference_basis"] = "A basis no ruling gives."
    _write(ruled.staged, record)
    with pytest.raises(SystemExit, match="Staged adjudications of the ruled outputs"):
        _verify(ruled)


SCENARIO_051 = "us__scenario_051__state_income_tax_before_refundable_credits"


def test_a_restated_scenario_051_passes_the_record_gate(ruled):
    """scenario_051 re-opened: the restate script restates its judge fields,
    then adjudicate-exclusions takes the ruling's decision fields in place."""
    record = ruled.record
    base = next(
        e
        for e in driver.base_adjudication_record()["adjudications"]
        if _case(e) == SCENARIO_051
    )
    _bind_current_verdict(ruled.cases, base)
    item = next(
        i
        for i in release_spec()["adjudications"]
        if case_dir_name(*driver.spec_key(i)) == SCENARIO_051
    )
    records = {driver.spec_key(r): r for r in release_exclusions()}
    entry = driver.exclusion_entry(
        _restated(base),
        item,
        records[driver.spec_key(item)],
        ruled.cases / SCENARIO_051,
    )
    index = next(
        i for i, e in enumerate(record["adjudications"]) if _case(e) == SCENARIO_051
    )
    record["adjudications"][index] = entry
    _write(ruled.staged, record)
    assert _verify(ruled, rejudged={SCENARIO_051}) == 0


def test_the_committed_base_record_is_in_the_committed_form():
    text = base_blob(ADJUDICATIONS_PATH).decode()
    assert text == driver.record_text(json.loads(text))


@pytest.mark.parametrize(
    "defect",
    ["duplicate_key", "note", "conventions", "compact", "unnamed_wave", "wave_twice"],
)
def test_bytes_the_entry_gate_cannot_see_are_refused(ruled, defect):
    """A duplicate key hides text a parser drops; the note and conventions are
    outside the entries; a record in another layout could hide either; and
    the conventions must name the 2026-10-06 wave exactly once."""
    record = ruled.record
    text = driver.record_text(record)
    base = driver.base_adjudication_record()
    if defect == "duplicate_key":
        text = text.replace(
            '"adjudicator": "developer"',
            '"adjudicator": "SMUGGLED", "adjudicator": "developer"',
            1,
        )
    elif defect == "note":
        record["note"] = "Rewritten."
        text = driver.record_text(record)
    elif defect == "conventions":
        record["date_conventions"] = {}
        text = driver.record_text(record)
    elif defect == "compact":
        text = json.dumps(record)
    elif defect == "unnamed_wave":
        record["date_conventions"] = base["date_conventions"]
        text = driver.record_text(record)
    else:
        record["date_conventions"] = driver.release_date_conventions(
            record["date_conventions"].replace(
                driver.DATE_CONVENTIONS_WAVES, driver.DATE_CONVENTIONS_BASE
            )
        )
        text = driver.record_text(record)
    ruled.staged.write_text(text)
    with pytest.raises(
        SystemExit, match="committed form|only entries may change|not release 20261006"
    ):
        _verify(ruled)


@pytest.fixture
def restated(tmp_path):
    """A re-opened entry restated as the restate script does, with its verdict."""
    base = driver.base_adjudications()
    entry = next(
        e
        for e in base
        if e["judge_model"] == driver.JUDGE_MODEL
        and e.get("judge_previous")
        and _case(e) not in _ruled_cases()
    )
    cases = tmp_path / "cases"
    _bind_current_verdict(cases, entry)
    staged = [_restated(e) if e is entry else e for e in base]
    index = next(i for i, e in enumerate(staged) if _case(e) == _case(entry))
    return base, staged, frozenset({_case(entry)}), cases, index


def test_a_restated_entry_passes_the_restatement_check(restated):
    base, staged, rejudged, cases, _ = restated
    driver.verify_restatements(base, staged, rejudged, cases)


# Each rewrites the appended item: the verdict the re-judge replaced must stay
# the one 20261006's entry names, as its seed sidecar records it.
APPENDED_ITEM_TAMPERS = {
    "appended_judged_on": {"judged_on": "2026-09-28"},
    "appended_class": {"judge_failure_source": "reference_error"},
    "appended_subtype": {"judge_failure_subtype": "other"},
    "appended_flag": {"judge_reference_suspect": "yes"},
    "appended_judge": {"judge_model": "claude-opus-5"},
    "appended_flag_source": {"judge_reference_suspect_source": "a-human-typed-this"},
}


@pytest.mark.parametrize(
    "tamper",
    [
        "judge_model",
        "emptied_history",
        "two_items",
        "rewritten_history",
        "day",
        *APPENDED_ITEM_TAMPERS,
    ],
)
def test_judge_fields_written_by_hand_are_refused(restated, tamper):
    base, staged, rejudged, cases, index = restated
    entry = copy.deepcopy(staged[index])
    if tamper == "judge_model":
        entry["judge_model"] = "a-human-typed-this"
    elif tamper == "emptied_history":
        entry["judge_previous"] = []
    elif tamper == "two_items":
        entry["judge_previous"] = entry["judge_previous"] + entry["judge_previous"][-1:]
    elif tamper == "rewritten_history":
        entry["judge_previous"][0] = {**entry["judge_previous"][0], "judged_on": "1999"}
    elif tamper in APPENDED_ITEM_TAMPERS:
        appended = entry["judge_previous"][-1]
        edit = APPENDED_ITEM_TAMPERS[tamper]
        assert all(appended.get(k) != v for k, v in edit.items())
        entry["judge_previous"][-1] = {**appended, **edit}
    else:
        entry["judge_rejudged_on"] = "1999-01-01"
    staged[index] = entry
    with pytest.raises(SystemExit, match="not restated by the restate script"):
        driver.verify_restatements(base, staged, rejudged, cases)


@pytest.fixture(scope="module")
def ruled_cases(tmp_path_factory):
    cases = tmp_path_factory.mktemp("ruled") / "cases"
    write_ruled_verdicts(cases)
    return cases


@functools.cache
def _gate_baseline(cases: Path) -> tuple[str, str, tuple[int, ...]]:
    """Release 20261006's entries and the ruled record's, and the indices of
    the ruled record's entries outside the ten."""
    from policybench.adjudications import parse_adjudications

    staged = parse_adjudications(ruled_record(cases), "ruled")
    outside = tuple(
        index for index, e in enumerate(staged) if _case(e) not in _ruled_cases()
    )
    return json.dumps(driver.base_adjudications()), json.dumps(staged), outside


@examples(200)
@given(
    pick_entry=st.integers(min_value=0, max_value=10**6),
    pick=st.integers(min_value=0, max_value=10**6),
    mutation=st.sampled_from(
        ["value", "delete", "add_decision_key", "add_judge_key", "swap_decisions"]
    ),
    reopened=st.booleans(),
)
def test_the_gate_allows_exactly_the_judge_fields_of_reopened_cases(
    ruled_cases, pick_entry, pick, mutation, reopened
):
    """For every entry outside the ten ruled ones and every kind of single
    change: a change to a judge field passes only where the case is
    re-opened; any other change fails."""
    from restate_gpt61sol_adjudications import JUDGE_FIELDS

    base_text, staged_text, outside = _gate_baseline(ruled_cases)
    base, staged = json.loads(base_text), json.loads(staged_text)
    index = outside[pick_entry % len(outside)]
    entry = staged[index]
    keys = list(entry)
    judge = mutation == "add_judge_key"
    if mutation in ("value", "delete"):
        key = keys[pick % len(keys)]
        judge = key in JUDGE_FIELDS
        if key in ("country", "scenario_id", "variable"):
            return  # a different case key is a dropped plus an added entry
        if mutation == "delete":
            del entry[key]
        else:
            entry[key] = [entry[key], "mutated"]
    elif mutation == "add_decision_key":
        entry["x_extra"] = "added"
    elif mutation == "add_judge_key":
        if "judged_on_utc" in entry:
            del entry["judged_on_utc"]
        else:
            entry["judged_on_utc"] = "2026-10-08"
    else:
        decisions = [k for k in keys if k not in JUDGE_FIELDS]
        first = decisions[pick % (len(decisions) - 1)]
        second = decisions[decisions.index(first) + 1]
        items = list(entry.items())
        i, j = keys.index(first), keys.index(second)
        items[i], items[j] = items[j], items[i]
        staged[index] = entry = dict(items)
    rejudged = frozenset({_case(entry)}) if reopened else frozenset()
    if reopened and judge:
        assert (
            driver.verify_adjudication_changes(base, staged, rejudged, [], ruled_cases)
            == 0
        )
    else:
        with pytest.raises(SystemExit, match="change recorded decisions"):
            driver.verify_adjudication_changes(base, staged, rejudged, [], ruled_cases)


# --- Wording amendments ----------------------------------------------------------


def _amendment(entry, old, new, field="reasoning", **extra):
    return {
        "case_id": _case(entry),
        "field": field,
        "old": old,
        "new": new,
        "reason": "The re-judge replaced the verdict this sentence describes.",
        **extra,
    }


def test_a_listed_wording_amendment_is_allowed_and_nothing_else(ruled):
    record = ruled.record
    entry = _unruled(record)[0]
    old = entry["reasoning"].split(". ")[0]
    amendment = _amendment(entry, old, old + ", as restated")
    original = copy.deepcopy(record)
    entry["reasoning"] = entry["reasoning"].replace(old, old + ", as restated")
    _write(ruled.staged, record)
    assert _verify(ruled, {_case(entry)}, [amendment]) == 0
    # Unlisted, the same change is refused.
    with pytest.raises(SystemExit, match="change recorded decisions"):
        _verify(ruled, {_case(entry)})
    # Listed but not applied, it is refused too: the list is exact.
    _write(ruled.staged, original)
    with pytest.raises(SystemExit, match="change recorded decisions"):
        _verify(ruled, {_case(entry)}, [amendment])
    # Any other change beside it is still refused.
    entry["adjudicated_on"] = "2026-10-06"
    _write(ruled.staged, record)
    with pytest.raises(SystemExit, match="change recorded decisions"):
        _verify(ruled, {_case(entry)}, [amendment])


def test_an_amendment_must_find_its_old_text_exactly_once(ruled):
    entry = _unruled(ruled.record)[0]
    for old in ("no such wording", " "):
        with pytest.raises(SystemExit, match="occurs"):
            _verify(ruled, {_case(entry)}, [_amendment(entry, old, "x")])


@pytest.fixture
def amendment_stage(tmp_path):
    entry = driver.base_adjudications()[0]
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / driver.PROMPT_CHANGES).write_text(
        json.dumps({"added": [], "changed": [_case(entry)], "kept": []})
    )

    def write(*items):
        (stage / driver.AMENDMENTS).write_text(json.dumps({"amendments": items}))
        return driver.load_amendments(stage, frozenset({_case(entry)}))

    return entry, write


def test_load_amendments_accepts_wording_of_rejudged_cases(amendment_stage):
    entry, write = amendment_stage
    items = [
        _amendment(entry, "a", "b"),
        _amendment(entry, "a", "b", field="case_annotation"),
        _amendment(entry, "a", "b", field="annotation", model=HAIKU),
    ]
    assert write(*items) == items


@pytest.mark.parametrize(
    "defect, message",
    [
        ({"field": "adjudicated_failure_source"}, "not wording"),
        ({"field": "excluded_from_scoring"}, "not wording"),
        ({"field": "judge_failure_source"}, "not wording"),
        ({"case_id": "us__scenario_999__snap"}, "not re-judged"),
        ({"reason": " "}, "reason"),
        ({"new": None}, "new"),
        ({"old": ""}, "old"),
        ({"new": "same", "old": "same"}, "changes nothing"),
        ({"model": HAIKU}, "keys"),
        ({"field": "annotation"}, "keys"),
    ],
)
def test_load_amendments_refuses_anything_but_wording_of_rejudged_cases(
    amendment_stage, defect, message
):
    entry, write = amendment_stage
    with pytest.raises(SystemExit, match=message):
        write({**_amendment(entry, "a", "b"), **defect})


def test_without_a_stage_list_the_amendments_record_is_release_20261006s(tmp_path):
    base = base_blob(ANNOTATIONS_DIR / AMENDMENTS_RECORD)
    assert release.committed_amendments(tmp_path) == base
    (tmp_path / driver.AMENDMENTS).write_text(json.dumps({"amendments": []}))
    assert release.committed_amendments(tmp_path) == base


AMENDMENT_ITEMS = st.fixed_dictionaries(
    {
        "case_id": st.sampled_from(["us__scenario_001__snap", "us__scenario_002__ssi"]),
        "field": st.sampled_from(["reasoning", "case_annotation"]),
        "old": st.text(min_size=1, max_size=5),
        "new": st.text(min_size=1, max_size=5),
        "reason": st.text(min_size=1, max_size=5),
    }
)


@examples(100)
@given(
    items=st.lists(AMENDMENT_ITEMS, min_size=1, max_size=4),
    note=st.none() | st.text(max_size=8),
)
def test_a_stage_list_is_appended_to_release_20261006s_amendments(
    tmp_path_factory, items, note
):
    """The earlier amendments stay, in order, before the stage's, and the
    note names how many are this release's; the bytes are in the committed
    form."""
    stage = tmp_path_factory.mktemp("amend")
    listed = (
        {"amendments": items} if note is None else {"note": note, "amendments": items}
    )
    (stage / driver.AMENDMENTS).write_text(json.dumps(listed))
    base = json.loads(base_blob(ANNOTATIONS_DIR / AMENDMENTS_RECORD))
    text = release.committed_amendments(stage)
    merged = json.loads(text)
    assert list(merged) == ["note", "amendments"]
    assert merged["amendments"] == base["amendments"] + items
    assert merged["note"].startswith(
        base["note"]
        + f" The last {len(items)} (after the first {len(base['amendments'])})"
    )
    if note is not None and note.strip():
        assert merged["note"].endswith(" " + note.strip())
    assert text == json.dumps(merged, indent=1, ensure_ascii=False).encode()


def test_the_freeze_commits_the_appended_amendments(frozen_board, monkeypatch):
    """A stage list, bound by the receipt, is committed after release
    20261006's amendments; verify_frozen checks the frozen record is that."""
    stage = frozen_board.stage
    item = {
        "case_id": KEPT,
        "field": "case_annotation",
        "old": "outdated",
        "new": "prior year's",
        "reason": "The re-judge reworded it.",
    }
    (stage / driver.AMENDMENTS).write_text(json.dumps({"amendments": [item]}))
    monkeypatch.setattr(driver, "rejudged_cases", lambda stage: frozenset({KEPT}))
    receipt = json.loads((stage / "release-ready.json").read_text())
    receipt["files"][driver.AMENDMENTS] = sha(stage / driver.AMENDMENTS)
    (stage / "release-ready.json").write_text(json.dumps(receipt))
    # The kept case is now re-opened: its verdict is new, bound to its prompt,
    # and the provenance record would list it; both gates are tested above.
    monkeypatch.setattr(release, "verify_verdicts", lambda stage: None)
    monkeypatch.setattr(release, "verify_judge_provenance", lambda *a: None)
    release.main(["--stage-dir", str(stage)])
    frozen = json.loads(
        (release.ROOT / ANNOTATIONS_DIR / AMENDMENTS_RECORD).read_text()
    )
    base = json.loads(base_blob(ANNOTATIONS_DIR / AMENDMENTS_RECORD))
    assert frozen["amendments"] == [*base["amendments"], item]
    assert frozen_board.checked == [[item]]


# One re-opened, decided case: its verdict's rationale and diagnoses are the
# sources triage folds into the published case note and row annotations.
WORDING_CASE = "us__scenario_001__snap"
RATIONALE = "The model applied an outdated threshold."
DIAGNOSES = {"m1": "It left out A. More.", "m2": "It used last year's threshold."}
DECISION = {
    "country": "us",
    "scenario_id": "scenario_001",
    "variable": "snap",
    "judge_model": "claude-opus-5-5",
    "judge_failure_source": "llm_error",
    "judge_failure_subtype": "thresholds_rates",
    "adjudicated_failure_source": "llm_error",
    "adjudicated_failure_subtype": "thresholds_rates",
    "adjudicated_on": "2026-10-06",
    "adjudicator": "developer",
    "reasoning": "The threshold is the current year's.",
}


def _row_amendment(old, new, model="m1"):
    return {
        "case_id": WORDING_CASE,
        "field": "annotation",
        "model": model,
        "old": old,
        "new": new,
        "reason": "r",
    }


def _note_amendment(old, new):
    return {
        "case_id": WORDING_CASE,
        "field": "case_annotation",
        "old": old,
        "new": new,
        "reason": "r",
    }


# A later amendment rewrites words an earlier one wrote.
CHAINED = [
    _row_amendment("It left out A.", "It left out A, as B does."),
    _row_amendment("as B does", "as the corrected B does"),
    _note_amendment("an outdated", "the prior year's"),
]
# What triage publishes with CHAINED applied, spelled out by hand.
PUBLISHED = {
    "m1": "It left out A, as the corrected B does. More.",
    "m2": DIAGNOSES["m2"],
    "note": "The model applied the prior year's threshold."
    + " Developer adjudication (2026-10-06): the judge (claude-opus-5-5) returned "
    "llm_error; adjudicated llm_error (thresholds_rates). The threshold is the "
    "current year's.",
}
# What triage publishes on the case with CHAINED applied when no adjudication
# decides it: the case note is the amended rationale alone.
UNDECIDED = {**PUBLISHED, "note": "The model applied the prior year's threshold."}


def _wording_stage(tmp_path, published, decided=True):
    """An audit with the case's verdict, the staged record deciding it (or,
    with ``decided`` false, deciding nothing), and the published case note
    and row annotations ``published`` spells, every column as triage writes
    it: the verdict's classes, which the decision affirms, beside the text."""
    import pandas as pd

    from policybench.adjudications import adjudication_sentence

    assert PUBLISHED["note"].endswith(adjudication_sentence(DECISION))
    audit = tmp_path / "audit"
    (audit / "cases" / WORDING_CASE).mkdir(parents=True)
    keys = {"country": "us", "scenario_id": "scenario_001", "variable": "snap"}
    (audit / "cases.jsonl").write_text(
        json.dumps(
            {
                "case_id": WORDING_CASE,
                "scenario_id": keys["scenario_id"],
                "variable": keys["variable"],
                "wrong_models": list(DIAGNOSES),
                "parse_failure_only": False,
            }
        )
        + "\n"
    )
    verdict = {
        "reference_suspect": False,
        "reference_bug_hypothesis": "",
        "case_failure_source": "llm_error",
        "case_failure_subtype": "thresholds_rates",
        "rationale": RATIONALE,
        "models": [
            {
                "model": model,
                "failure_source": "llm_error",
                "failure_subtype": "thresholds_rates",
                "diagnosis": diagnosis,
            }
            for model, diagnosis in DIAGNOSES.items()
        ],
    }
    (audit / "cases" / WORDING_CASE / "verdict.json").write_text(json.dumps(verdict))
    annotations = tmp_path / "publish" / RUN / "annotations"
    annotations.mkdir(parents=True)
    (annotations / ADJUDICATIONS).write_text(
        json.dumps({"adjudications": [DECISION] if decided else []})
    )
    classes = {"failure_source": "llm_error", "failure_subtype": "thresholds_rates"}
    pd.DataFrame(
        [
            {
                **keys,
                "model": model,
                **classes,
                "reference_suspect": False,
                "annotation": published[model],
            }
            for model in DIAGNOSES
            if model in published
        ]
    ).to_csv(annotations / ROWS, index=False)
    note = {
        **keys,
        "wrong_model_count": len(DIAGNOSES),
        "case_failure_sources": "llm_error",
        "case_failure_subtypes": "thresholds_rates",
        "reference_suspect": False,
        "reference_bug_hypothesis": "",
        "case_annotation": published["note"],
    }
    pd.DataFrame([note]).to_csv(annotations / NOTES, index=False)
    return annotations, audit


def test_the_freeze_replays_chained_amendments_onto_the_sources(tmp_path):
    """Each text is rebuilt from its verdict source and the adjudication
    sentence, the amendments replayed in order; the full result must be the
    published text, and a text no amendment names must be its source."""
    annotations, audit = _wording_stage(tmp_path, PUBLISHED)
    release.verify_annotation_amendments(annotations, CHAINED, audit)


@pytest.mark.parametrize(
    "published, amendments",
    [
        # The listed fragment is present, beside wording nobody listed.
        ({**PUBLISHED, "m1": PUBLISHED["m1"] + " Unlisted."}, CHAINED),
        ({**PUBLISHED, "note": "Unlisted. " + PUBLISHED["note"]}, CHAINED),
        # A text no amendment names, reworded.
        ({**PUBLISHED, "m2": "It used an unlisted threshold."}, CHAINED),
        ({**PUBLISHED, "m2": DIAGNOSES["m2"] + " Unlisted."}, CHAINED),
        # With no amendments at all, every text is still checked.
        ({**PUBLISHED, "m1": DIAGNOSES["m1"] + " Unlisted."}, []),
        # A listed amendment not applied, or only half of a chain.
        ({**PUBLISHED, "m1": DIAGNOSES["m1"]}, CHAINED),
        ({**PUBLISHED, "m1": "It left out A, as B does. More."}, CHAINED),
        # A published row annotation dropped.
        ({key: text for key, text in PUBLISHED.items() if key != "m2"}, CHAINED),
    ],
)
def test_the_freeze_refuses_wording_the_amendments_do_not_produce(
    tmp_path, published, amendments
):
    annotations, audit = _wording_stage(tmp_path, published)
    with pytest.raises(SystemExit, match="is not what triage builds"):
        release.verify_annotation_amendments(annotations, amendments, audit)


def test_each_replayed_old_text_must_occur_once_when_applied(tmp_path):
    """The first amendment makes the second's old text occur twice."""
    twice = [
        _row_amendment("It left out A.", "It left out A. A."),
        _row_amendment("A.", "B."),
    ]
    annotations, audit = _wording_stage(
        tmp_path, {**PUBLISHED, "m1": "It left out B. A. More."}
    )
    with pytest.raises(SystemExit, match="occurs 2 times"):
        release.verify_annotation_amendments(annotations, twice, audit)


def test_an_undecided_case_publishes_its_verdict_sources(tmp_path):
    annotations, audit = _wording_stage(tmp_path, UNDECIDED, decided=False)
    release.verify_annotation_amendments(annotations, CHAINED, audit)


# Each column triage publishes beside the wording, changed on the case: its
# rows' classes and flag, and its note's classes, flag, count and hypothesis.
COLUMN_EDITS = [
    (ROWS, "failure_source", "prompt_ambiguity"),
    (ROWS, "failure_subtype", "missing_output"),
    (ROWS, "reference_suspect", "True"),
    (NOTES, "case_failure_sources", "prompt_ambiguity"),
    (NOTES, "case_failure_subtypes", "missing_output"),
    (NOTES, "reference_suspect", "True"),
    (NOTES, "wrong_model_count", "3"),
    (NOTES, "reference_bug_hypothesis", "The reference is wrong."),
]


@pytest.mark.parametrize("decided", [False, True])
@pytest.mark.parametrize("name, column, value", COLUMN_EDITS)
def test_the_freeze_refuses_any_column_triage_did_not_write(
    tmp_path, decided, name, column, value
):
    """The texts unchanged, any other published column that is not the
    verdict's (or, on a decided case, the adjudication's) is refused, and
    named by its case and column."""
    import pandas as pd

    annotations, audit = _wording_stage(
        tmp_path, PUBLISHED if decided else UNDECIDED, decided=decided
    )
    frame = pd.read_csv(annotations / name, dtype=str, keep_default_na=False)
    frame.loc[0, column] = value
    frame.to_csv(annotations / name, index=False)
    with pytest.raises(
        SystemExit,
        match=rf"{re.escape(name)} is not what triage builds.*{WORDING_CASE}\S* "
        rf"{column}",
    ):
        release.verify_annotation_amendments(annotations, CHAINED, audit)


@pytest.mark.parametrize("defect", ["dropped_column", "extra_column", "row_order"])
def test_the_freeze_refuses_columns_or_rows_triage_did_not_write(tmp_path, defect):
    import pandas as pd

    annotations, audit = _wording_stage(tmp_path, PUBLISHED)
    path = annotations / ROWS
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if defect == "dropped_column":
        frame = frame.drop(columns=["failure_subtype"])
        problem = "its columns"
    elif defect == "extra_column":
        frame["reviewed"] = "yes"
        problem = "its columns"
    else:
        frame = frame.iloc[::-1]
        problem = "its row order or serialization"
    frame.to_csv(path, index=False)
    with pytest.raises(SystemExit, match=f"differs at.*{problem}"):
        release.verify_annotation_amendments(annotations, CHAINED, audit)


# --- Treatment -----------------------------------------------------------------


def test_the_registered_treatment_matches_the_run_and_a_drift_is_refused(tmp_path):
    state = {"model": HAIKU, "treatment_fingerprint": HAIKU_FINGERPRINT}
    path = tmp_path / "run_state.json"
    scenarios = driver.SNAPSHOT / "scenarios.csv"
    release.validate_treatment(freezer, state, path, scenarios)
    drifted = copy.deepcopy(state)
    drifted["treatment_fingerprint"]["request_timeout_seconds"] = 600
    with pytest.raises(SystemExit, match="disagrees with registry"):
        release.validate_treatment(freezer, drifted, path, scenarios)


def test_the_live_runs_fingerprint_is_the_one_these_tests_pin():
    """(local: the stage is gitignored)"""
    state = REPO / "results/local/release-haiku55/stage/inputs/haiku55/run_state.json"
    if not state.is_file():
        pytest.skip("no live stage in this checkout")
    assert json.loads(state.read_text())["treatment_fingerprint"] == HAIKU_FINGERPRINT
