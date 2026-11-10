"""Claude Fable 5.2's release keeps Terra's gates, installs no build and
excludes one more output: Max's d2180, scenario_122's Minnesota
state_refundable_credits.

MOCK DATA: every run, audit, stage, verdict and payload below is synthetic.
The mock boards take the committed references and scenarios of three
households (read from git at the base commit) and invent every model's
answers and failure annotations; the exporter, the dashboard validator and
the scope check run for real on them. The committed snapshot, references and
records are only read. Nothing writes published data or calls an engine,
provider or network service.
"""

from __future__ import annotations

import ast
import copy
import datetime as dt
import functools
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from hypothesis import HealthCheck, assume, example, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import finish_fable52 as driver  # noqa: E402
import release_20261006  # noqa: E402

from policybench.audit import AUDIT_OUTPUT_SCHEMA  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
NEW, SLUG = "claude-fable-5.2", "fable52"
RUN = driver.RUN_NAME
SNAPSHOT_PATH = Path("paper/snapshot/20260501/runs") / RUN
ANNOTATIONS_PATH = Path("annotations") / RUN
CSV_NAME = "reference_outputs.csv"
META_NAME = "reference_outputs.csv.meta.json"
EXCLUSIONS_NAME = "reference_exclusions.json"
BOUND = f"publish/{RUN}/us/{EXCLUSIONS_NAME}"
RULED = ("scenario_122", "state_refundable_credits")
TAIL = ("scenario_023", "head_medicaid_eligible")
# build_release_exclusions(base_exclusion_record(), docs/fable52/spec.json),
# spelled by exclusions_text: the one record this release scores on.
RELEASE_EXCLUSIONS_SHA256 = (
    "7b965a303e809c095a80679ebe981a75354138963e4ee75d14e4a475b3ef90f0"
)
# MOCK days standing in for the lead's: the spec holds "[LEAD: ...]" for both.
WRITTEN_ON = "2026-11-10"
SNAPSHOT_DATE = "2026-11-10"


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


# The placeholders the committed spec holds until the lead fills each day.
SNAPSHOT_PLACEHOLDER = "[LEAD: the UTC day of the freeze, YYYY-MM-DD]"
WRITTEN_PLACEHOLDER = (
    "[LEAD: the UTC day --step adjudicate-exclusions runs, YYYY-MM-DD]"
)


def filled_spec(**changes) -> dict:
    """The spec as the lead fills it before the steps that read its days,
    with no triage decision: a test of the triage wave adds its own."""
    spec = real_spec()
    spec.update(
        {
            "snapshot_date": SNAPSHOT_DATE,
            "adjudications_written_on": WRITTEN_ON,
            "triage_adjudications": [],
        }
    )
    spec.update(changes)
    return spec


# Read once under the checkout's own root: several fixtures below move
# driver.ROOT to a synthetic checkout, as Terra's tests did.
BASE_RECORD = driver.base_exclusion_record()


def base_record() -> dict:
    """Release 20261027's exclusion record, read and pin-checked by the driver."""
    return copy.deepcopy(BASE_RECORD)


def release_record() -> dict:
    return driver.build_release_exclusions(base_record(), real_spec())


def release_text() -> str:
    return driver.exclusions_text(release_record())


@pytest.fixture(autouse=True)
def cached_base_blobs(monkeypatch):
    """Every base read names one immutable commit: reuse its git bytes."""
    monkeypatch.setattr(driver, "base_commit_blob", base_blob)


@pytest.fixture
def filled(monkeypatch):
    spec = filled_spec()
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    return spec


# --- The release: one model and one ruled record on release 20261027 ---------


def test_fable52_alone_joins_the_51_model_base():
    assert driver.MODELS == {SLUG: NEW}
    assert (driver.BASE_MODELS, driver.BOARD_MODELS) == (51, 52)
    assert (driver.BASE_OUTPUTS, driver.BASE_EXCLUSIONS, driver.BASE_SCORED) == (
        1984,
        49,
        1935,
    )
    assert (
        driver.NEW_EXCLUSIONS,
        driver.RELEASE_EXCLUSIONS,
        driver.RELEASE_SCORED,
    ) == (1, 50, 1934)
    assert driver.BASE_TAG == "dashboard-data-20261027"
    assert driver.RELEASE_TAG == "dashboard-data-20261110"
    assert driver.BASE_COMMIT == "875fe1f6f59f4d584b500ca193b60838d3bdf14c"
    assert driver.SEED_RELEASE_COMMIT == driver.BASE_COMMIT
    assert driver.JUDGE_MODEL == "claude-opus-5-5"
    assert driver.JUDGE_TEMPLATE_VERSION == 2
    assert driver.REWORDED_SINCE_SEED == frozenset()
    assert driver.BASE_ENGINE == "policyengine-us 2.60.0"
    assert driver.CARRIED_USAGE == release_20261006.CARRIED_USAGE
    assert driver.JUDGE_PROVENANCE_PATH.startswith("docs/fable52/")
    assert driver.INPUT_PINS_PATH.startswith("docs/fable52/")


def test_the_release_tag_is_defined_once_in_the_drivers():
    source = (REPO / "scripts/finish_fable52.py").read_text()
    assert source.count(driver.RELEASE_TAG) == 1
    for name in ("freeze_fable52.py", "date_fable52_judge_verdicts.py"):
        assert driver.RELEASE_TAG not in (REPO / "scripts" / name).read_text()


def test_the_base_pointer_and_the_spec_name_release_20261027():
    pointer = json.loads(base_blob(Path("app/src/data.artifact.json")))
    assert (pointer["tag"], pointer["sha256"]) == (driver.BASE_TAG, driver.BASE_SHA256)
    spec = real_spec()
    assert (spec["release_tag"], spec["base_tag"], spec["base_sha256"]) == (
        driver.RELEASE_TAG,
        driver.BASE_TAG,
        driver.BASE_SHA256,
    )


def test_the_seed_digest_is_release_20261027s_681_judged_cases():
    text = driver.SEED_DIGEST.read_bytes()
    assert sha(text) == driver.SEED_DIGEST_SHA256
    header, *rows = text.decode().splitlines()
    assert header == "case_id,prompt_sha256,verdict_sha256" and len(rows) == 681
    seed = {}
    for row in rows:
        case, prompt, verdict = row.split(",")
        seed[case] = {"prompt_sha256": prompt, "verdict_sha256": verdict}
    assert driver.seed_digest_text(seed).encode() == text
    driver.verify_seed(seed)
    seed.pop(rows[0].split(",")[0])
    with pytest.raises(SystemExit, match="is not release 20261027's"):
        driver.verify_seed(seed)


# --- References: release 20261027's bytes at every step -----------------------


def test_the_reference_pins_are_release_20261027s_committed_bytes(tmp_path):
    directory = base_references(tmp_path / "base")
    driver.verify_reference_pins(directory, "base")
    assert set(driver.BASE_REFERENCE_SHA256) == set(driver.REFERENCE_FILES)
    assert {
        name: sha(directory / name) for name in driver.REFERENCE_FILES
    } == driver.BASE_REFERENCE_SHA256


def test_the_checkout_holds_the_base_references_or_the_frozen_release_record():
    for name, pin in driver.BASE_REFERENCE_SHA256.items():
        allowed = {pin}
        if name == EXCLUSIONS_NAME:
            allowed.add(RELEASE_EXCLUSIONS_SHA256)
        assert sha(driver.SNAPSHOT / name) in allowed, name


@pytest.mark.parametrize("name", driver.REFERENCE_FILES)
@pytest.mark.parametrize("edit", ["flipped", "appended", "missing"])
def test_a_reference_file_or_sidecar_off_the_base_is_refused(tmp_path, name, edit):
    directory = base_references(tmp_path / "staged")
    path = directory / name
    if edit == "flipped":
        data = bytearray(path.read_bytes())
        data[len(data) // 2] ^= 1
        path.write_bytes(bytes(data))
    elif edit == "appended":
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        path.unlink()
    with pytest.raises(SystemExit, match=rf"{re.escape(name)} does not match its pin"):
        driver.verify_reference_pins(directory, "staged reference")


@pytest.fixture(scope="module")
def pinned_directory(tmp_path_factory):
    return base_references(tmp_path_factory.mktemp("pinned"))


@settings(max_examples=40, deadline=None)
@given(
    name=st.sampled_from(driver.REFERENCE_FILES),
    where=st.floats(0, 1, exclude_max=True),
    flip=st.integers(1, 255),
)
def test_any_one_byte_change_to_a_reference_file_is_refused(
    pinned_directory, name, where, flip
):
    path = pinned_directory / name
    original = path.read_bytes()
    data = bytearray(original)
    data[int(where * len(data))] ^= flip
    try:
        path.write_bytes(bytes(data))
        with pytest.raises(SystemExit, match="does not match its pin"):
            driver.verify_reference_pins(pinned_directory, "staged reference")
    finally:
        path.write_bytes(original)
    driver.verify_reference_pins(pinned_directory, "staged reference")


def test_later_steps_take_the_release_record_and_refuse_the_bases(tmp_path):
    directory = base_references(tmp_path / "staged")
    release = driver.release_exclusions_sha256()
    with pytest.raises(SystemExit, match="reference_exclusions.json does not match"):
        driver.verify_reference_pins(directory, "staged reference", release)
    (directory / EXCLUSIONS_NAME).write_text(release_text())
    driver.verify_reference_pins(directory, "staged reference", release)
    with pytest.raises(SystemExit, match="reference_exclusions.json does not match"):
        driver.verify_reference_pins(directory, "staged reference")


# --- The base's engine and the audit's publication record ---------------------

TIMING = driver.REFERENCE_AUDIT / "verification/sweep_timing.json"
BUILDER = driver.REFERENCE_AUDIT / "scripts/build_references_upgrade.py"


@pytest.fixture
def engine_root(tmp_path):
    """A synthetic checkout root: copies of the committed files the base-engine
    and publication-record gates read."""
    root = tmp_path / "root"
    record = json.loads((REPO / TIMING).read_text())["publication_check"]
    built = [name for name in record["build_sha256"] if name != "builder"]
    for relative in (
        Path("pyproject.toml"),
        Path("uv.lock"),
        SNAPSHOT_PATH / META_NAME,
        BUILDER,
        TIMING,
        *(driver.REFERENCE_BUILD_DIR / name for name in built),
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    return root


def _edit_record(root: Path, edit) -> None:
    path = root / TIMING
    timing = json.loads(path.read_text())
    edit(timing["publication_check"])
    path.write_text(json.dumps(timing))


def test_the_base_engine_and_publication_record_pass_on_the_committed_files(
    engine_root,
):
    driver.verify_base_engine(engine_root)
    record = driver.verify_publication_record(engine_root)
    assert {
        name: record["build_sha256"][name] for name in driver.BUILD_REFERENCE_FILES
    } == {
        name: driver.BASE_REFERENCE_SHA256[name]
        for name in driver.BUILD_REFERENCE_FILES
    }
    # And on this checkout, as prepare and every later step read them.
    driver.verify_base_engine()
    driver.verify_publication_record()


def test_a_committed_sidecar_off_the_base_stops_the_base_engine_gate(engine_root):
    path = engine_root / SNAPSHOT_PATH / META_NAME
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(SystemExit, match=f"committed {re.escape(META_NAME)} is not"):
        driver.verify_base_engine(engine_root)


@pytest.mark.parametrize(
    "name, old, new, message",
    [
        (
            "pyproject.toml",
            "policyengine-us==2.60.0",
            "policyengine-us==2.61.0",
            "pyproject policyengine-us pin",
        ),
        ("uv.lock", 'version = "2.60.0"', 'version = "2.61.0"', "uv.lock policyengine"),
    ],
)
def test_a_project_pin_off_the_base_engine_is_refused(
    engine_root, name, old, new, message
):
    path = engine_root / name
    text = path.read_text()
    assert old in text
    path.write_text(text.replace(old, new, 1))
    with pytest.raises(SystemExit, match=message):
        driver.verify_base_engine(engine_root)


def _set(field, value):
    return lambda record: record.__setitem__(field, value)


def _pin(name, value):
    return lambda record: record["build_sha256"].__setitem__(name, value)


@pytest.mark.parametrize(
    "edit, accepted",
    [
        (_set("engine", "2.60.0"), True),
        (lambda r: r.update(engine="2.60.0", scored_differ=["moved"]), True),
        (lambda r: r.update(engine="9.0.0", scored_differ=[]), True),
        (lambda r: r.update(engine="9.0.0", scored_differ=[["scenario_122"]]), False),
        (lambda r: r.update(engine="9.0.0", scored_differ=None), False),
        (_set("engine", "2.59.9"), False),
        (_set("engine", "unknown"), False),
        (_pin(CSV_NAME, "0" * 64), False),
        (_pin(META_NAME, "0" * 64), False),
        (_pin(EXCLUSIONS_NAME, RELEASE_EXCLUSIONS_SHA256), False),
        (_pin("builder", "0" * 64), False),
        (lambda r: r["build_sha256"].pop(CSV_NAME), False),
    ],
)
def test_the_publication_record_must_name_the_bases_build_and_a_safe_engine(
    engine_root, edit, accepted
):
    _edit_record(engine_root, edit)
    if accepted:
        driver.verify_publication_record(engine_root)
    else:
        with pytest.raises(SystemExit, match="publication record disagrees"):
            driver.verify_publication_record(engine_root)


def test_the_publication_record_must_exist_and_its_build_must_be_committed(
    engine_root,
):
    built = engine_root / driver.REFERENCE_BUILD_DIR / "computed.csv"
    built.write_bytes(built.read_bytes() + b"\n")
    with pytest.raises(SystemExit, match="publication record disagrees"):
        driver.verify_publication_record(engine_root)
    _edit_record(engine_root, lambda record: record.clear())
    with pytest.raises(SystemExit, match="no publication_check record"):
        driver.verify_publication_record(engine_root)


def test_the_audits_builder_must_keep_its_pin(engine_root):
    path = engine_root / BUILDER
    path.write_text(path.read_text() + "# edited\n")
    with pytest.raises(SystemExit, match="builder is off its pin"):
        driver.verify_publication_record(engine_root)


# --finalize holds the record to a check of PyPI's newest engine, run on or
# after the snapshot day. These tests start from release 20261027's record,
# read from git: the lead's rerun rewrites the working tree's.


@pytest.fixture
def base_timing_root(engine_root):
    (engine_root / TIMING).write_bytes(base_blob(TIMING))
    return engine_root


def _edit_timing(root: Path, edit) -> None:
    path = root / TIMING
    timing = json.loads(path.read_text())
    edit(timing)
    path.write_text(json.dumps(timing))


def _read(stamp, newest="2.78.0"):
    return lambda timing: timing["pypi"].update(
        read_at_utc=stamp, newest_at_read=newest
    )


@pytest.mark.parametrize(
    "edit, day, accepted",
    [
        # Release 20261027's record read PyPI on 2026-10-29, newest 2.78.0.
        (lambda timing: None, "2026-10-29", True),
        (lambda timing: None, "2026-10-28", True),
        (lambda timing: None, "2026-10-30", False),
        (lambda timing: None, SNAPSHOT_DATE, False),
        (_read("2026-11-10T00:00:00Z"), SNAPSHOT_DATE, True),
        (_read("2026-11-09T23:59:59Z"), SNAPSHOT_DATE, False),
        (_read("2026-11-12T08:00:00Z", newest="2.80.0"), SNAPSHOT_DATE, False),
        (_read("2026-11-10T12:00:00+00:00"), SNAPSHOT_DATE, False),
        (_read("2026-11-10 12:00:00"), SNAPSHOT_DATE, False),
        (_read("2026-11-31T12:00:00Z"), SNAPSHOT_DATE, False),
        (_read(None), SNAPSHOT_DATE, False),
        (_read("2026-11-10T12:00:00Z", newest=None), SNAPSHOT_DATE, False),
        (lambda timing: timing.pop("pypi"), SNAPSHOT_DATE, False),
        # PyPI's newest is still the reference engine: the check records it.
        (
            lambda timing: (
                timing["publication_check"].update(engine="2.60.0"),
                timing["pypi"].update(
                    read_at_utc="2026-11-10T09:00:00Z", newest_at_read="2.60.0"
                ),
            ),
            SNAPSHOT_DATE,
            True,
        ),
    ],
)
def test_at_finalize_the_record_checks_pypis_newest_on_the_snapshot_day(
    base_timing_root, edit, day, accepted
):
    _edit_timing(base_timing_root, edit)
    # The record gate alone takes every one of these records.
    driver.verify_publication_record(base_timing_root)
    if accepted:
        driver.verify_publication_record(base_timing_root, checked_on_or_after=day)
    else:
        with pytest.raises(SystemExit, match="does not check the newest"):
            driver.verify_publication_record(base_timing_root, checked_on_or_after=day)


@pytest.mark.parametrize(
    "day", [SNAPSHOT_PLACEHOLDER, "", "2026-11-1", "10 November 2026", 20261110]
)
def test_at_finalize_the_record_needs_a_real_day(base_timing_root, day):
    with pytest.raises(SystemExit, match="no day to hold the publication check to"):
        driver.verify_publication_record(base_timing_root, checked_on_or_after=day)


@settings(
    max_examples=60,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(read=st.dates(), day=st.dates())
def test_the_currency_check_is_the_read_day_against_the_snapshot_day(
    base_timing_root, read, day
):
    """For any PyPI read day and snapshot day, a record of PyPI's newest engine
    passes exactly when the read falls on or after the snapshot day. Each
    example rewrites the root's whole record."""
    (base_timing_root / TIMING).write_bytes(base_blob(TIMING))
    _edit_timing(base_timing_root, _read(f"{read.isoformat()}T12:00:00Z"))
    if read >= day:
        driver.verify_publication_record(
            base_timing_root, checked_on_or_after=day.isoformat()
        )
    else:
        with pytest.raises(SystemExit, match="does not check the newest"):
            driver.verify_publication_record(
                base_timing_root, checked_on_or_after=day.isoformat()
            )


# --- The ruled record and the release's exclusion record ----------------------


def test_the_spec_rules_one_proposal_and_leaves_both_days_to_the_lead():
    """The committed spec as it stands at any point of the release: the lead
    fills each day before the step that reads it, and may add triage
    decisions (the gates hold their form), so either state passes here."""
    spec = real_spec()
    assert set(spec) <= driver.SPEC_KEYS
    (proposal,) = spec["proposals"]
    assert proposal["outputs"] == [list(RULED)]
    assert sha(REPO / proposal["path"]) == proposal["sha256"]
    assert [driver.spec_key(item) for item in spec["adjudications"]] == [RULED]
    assert spec["restated_adjudications"] == []
    assert isinstance(spec["triage_adjudications"], list)
    assert spec["decided_on"] == "2026-11-01"
    # Each day is the lead's placeholder, on which every gate that reads it
    # stops (the tests below run the gates on copies), or a real UTC day on
    # or after the ruling's.
    for key, placeholder in (
        ("snapshot_date", SNAPSHOT_PLACEHOLDER),
        ("adjudications_written_on", WRITTEN_PLACEHOLDER),
    ):
        day = driver.utc_day(spec[key])
        assert spec[key] == placeholder or (day is not None and day >= "2026-11-01")


def test_the_ruled_record_is_d2180s_on_the_references_engine():
    (record,) = driver.spec_records(real_spec())
    proposal = json.loads((REPO / "docs/fable52/proposed_exclusions.json").read_text())
    assert record == proposal["exclusions"][0]
    assert driver.spec_key(record) == RULED
    assert record["reason_code"] == "reference_depends_on_unlisted_input"
    assert (record["frozen_value"], record["alternative_value"]) == (0.0, 1921.0)
    assert (record["engine_version"], record["decided_on"], record["decided_by"]) == (
        driver.BASE_ENGINE,
        "2026-11-01",
        "developer",
    )
    reference = pd.read_csv(io.BytesIO(base_blob(SNAPSHOT_PATH / CSV_NAME)))
    value = reference.loc[
        (reference.scenario_id == RULED[0]) & (reference.variable == RULED[1]),
        "value",
    ]
    assert value.tolist() == [record["frozen_value"]]


# --- The ruled record against its audit's files (review r1, M18: E F6) ---------

CRP_AUDIT = Path("reference_audit/2026-10-29-mn-renters-crp/verification")
# Each engine's sweep with its trace (the record cites both).
CRP_RUNS = (
    ("crp_sweep.json", "trace_122_2_60_0.json", "policyengine-us 2.60.0"),
    ("crp_sweep_2_41_0.json", "trace_122_2_41_0.json", "policyengine-us 2.41.0"),
)


def _dollars(text: str) -> list[float]:
    """Each dollar figure in ``text``, in order."""
    return [
        float(figure.replace(",", ""))
        for figure in re.findall(r"\$(\d[\d,]*(?:\.\d+)?)", text)
    ]


def _row(frame: pd.DataFrame) -> list[float]:
    selected = (frame.scenario_id == RULED[0]) & (frame.variable == RULED[1])
    return frame.loc[selected, "value"].tolist()


def test_the_ruled_record_states_what_its_audit_computed():
    """A differential check of d2180's record and the spec's reasoning
    against the 2026-10-29 audit's files, read from release 20261027's
    commit (the release changes none of them): each engine's sweep moves the
    ruled output alone, from the committed reference to the record's
    alternative; each trace gives the record's two values; and each dollar
    figure the record and the reasoning quote is the 2.60.0 trace's, or the
    prompt's rent."""
    from policybench.prompts import describe_household
    from policybench.scenarios import scenario_from_dict

    spec = real_spec()
    (record,) = driver.spec_records(spec)
    (item,) = spec["adjudications"]
    audit = {}
    for name in (name for run in CRP_RUNS for name in run[:2]):
        audit[name] = json.loads(base_blob(CRP_AUDIT / name))
        assert (REPO / CRP_AUDIT / name).read_bytes() == base_blob(CRP_AUDIT / name)
    frozen, alternative = record["frozen_value"], record["alternative_value"]
    committed = pd.read_csv(io.BytesIO(base_blob(SNAPSHOT_PATH / CSV_NAME)))
    assert _row(committed) == [frozen]
    for sweep_name, trace_name, engine in CRP_RUNS:
        sweep, trace = audit[sweep_name], audit[trace_name]
        assert sweep["engine"] == trace["engine"] == engine
        assert sweep["harness"]["sha256"] == sha(REPO / sweep["harness"]["path"])
        assert RULED[0] in sweep["minnesota_households"]
        assert sweep["baseline_mismatches"] == []
        (moved,) = sweep["moved"]
        assert (moved["scenario_id"], moved["variable"], moved["scored"]) == (
            *RULED,
            True,
        )
        assert moved["reference"] == moved["as_built"] == frozen
        assert moved["with_crp"] == alternative
        assert trace["scenario"] == RULED[0]
        built, crp = trace["as_built"], trace["with_qualifying_crp"]
        assert (
            built["mn_renters_credit_qualifying_crp"],
            crp["mn_renters_credit_qualifying_crp"],
        ) == (False, True)
        assert (
            built["mn_renters_credit_eligible"],
            crp["mn_renters_credit_eligible"],
        ) == (
            False,
            True,
        )
        assert built["mn_renters_credit"] == built["mn_refundable_credits"] == frozen
        assert crp["mn_renters_credit"] == crp["mn_refundable_credits"] == alternative
        for name in (
            "mn_renters_credit_household_income",
            "mn_rent_constituting_property_taxes",
            "mn_renters_credit_property_tax_exempt",
        ):
            assert built[name] == crp[name], (trace_name, name)
    # The record's engine is the 2.60.0 sweep's, which ran against the
    # 2026-10-22 build; that build's row is the committed one.
    current = audit["crp_sweep.json"]
    assert record["engine_version"] == current["engine"] == driver.BASE_ENGINE
    build = Path(current["references"])
    assert build == Path("reference_audit/2026-10-22-engine-upgrade/reference-build")
    assert _row(pd.read_csv(io.BytesIO(base_blob(build / CSV_NAME)))) == [frozen]
    # Every figure the record and the reasoning quote.
    trace = audit["trace_122_2_60_0.json"]["as_built"]
    income = trace["mn_renters_credit_household_income"]
    threshold = audit["trace_122_2_60_0.json"]["max_credit_first_zero_threshold"]
    assert income < threshold
    scenarios = pd.read_csv(
        io.BytesIO(base_blob(SNAPSHOT_PATH / "scenarios.csv")), low_memory=False
    )
    (household,) = scenarios.loc[scenarios.scenario_id == RULED[0], "scenario_json"]
    described = describe_household(scenario_from_dict(json.loads(household)))
    assert "- state: MN" in described.splitlines()
    rent_line = [line for line in described.splitlines() if "pre-subsidy rent" in line]
    assert rent_line == ["- pre-subsidy rent: $28,235"]
    (rent,) = _dollars(rent_line[0])
    assert not re.search(r"certificate|\bcrp\b|rent paid", described, re.IGNORECASE)
    assert _dollars(record["alternative_reading"]) == [
        rent,
        income,
        threshold,
        trace["mn_rent_constituting_property_taxes"],
        alternative,
    ]
    assert _dollars(record["note"]) == [frozen, alternative]
    assert item["reasoning"].startswith(
        f"The frozen reference is {frozen:,.2f}; the alternative is "
        f"{alternative:,.2f}. "
    )
    assert _dollars(item["reasoning"]) == [rent, income, threshold, alternative]


def test_the_release_record_is_the_base_with_the_ruled_record_before_its_tail():
    base = driver.base_exclusion_record()
    assert driver.exclusions_text(base).encode() == base_blob(
        SNAPSHOT_PATH / EXCLUSIONS_NAME
    )
    release = release_record()
    before, after = base["exclusions"], release["exclusions"]
    assert (len(before), len(after)) == (49, 50)
    assert json.dumps(after[:48]) == json.dumps(before[:48])
    assert json.dumps(after[-1]) == json.dumps(before[-1])
    assert (driver.spec_key(after[-2]), driver.spec_key(after[-1])) == (RULED, TAIL)
    assert {
        k: v for k, v in release.items() if k not in ("exclusions", "derivation")
    } == {k: v for k, v in base.items() if k not in ("exclusions", "derivation")}
    insert = real_spec()["derivation_insert"]
    assert release["derivation"] == base["derivation"].replace(
        insert["before"], insert["text"] + insert["before"]
    )
    assert (
        sha(release_text().encode())
        == driver.release_exclusions_sha256()
        == RELEASE_EXCLUSIONS_SHA256
    )


@pytest.mark.parametrize(
    "key", ["upgrade_adjudications", "upgrade_adjudications_written_on", "stray"]
)
def test_a_spec_with_a_key_this_release_does_not_read_is_refused(
    tmp_path, monkeypatch, key
):
    root = tmp_path / "root"
    (root / driver.SPEC_PATH).parent.mkdir(parents=True)
    (root / driver.SPEC_PATH).write_text(json.dumps({**real_spec(), key: []}))
    monkeypatch.setattr(driver, "ROOT", root)
    with pytest.raises(SystemExit, match="holds keys this release does not read"):
        driver.load_spec()


def proposal_spec(tmp_path, monkeypatch, *, edit=None, extra=(), outputs=None):
    """The real spec, its proposal rewritten under a synthetic root (MOCK)."""
    root = tmp_path / "root"
    path = root / "docs/fable52/proposed_exclusions.json"
    path.parent.mkdir(parents=True)
    proposal = json.loads((REPO / "docs/fable52/proposed_exclusions.json").read_text())
    if edit is not None:
        edit(proposal["exclusions"][0])
    proposal["exclusions"].extend(extra)
    path.write_text(json.dumps(proposal, indent=2))
    monkeypatch.setattr(driver, "ROOT", root)
    spec = real_spec()
    spec["proposals"][0]["sha256"] = sha(path)
    if outputs is not None:
        spec["proposals"][0]["outputs"] = outputs
    return spec


def _another_record(scenario="scenario_000", variable="snap") -> dict:
    record = copy.deepcopy(driver.spec_records(real_spec())[0])
    record.update(scenario_id=scenario, variable=variable)
    return record


@pytest.mark.parametrize(
    "case, message",
    [
        ("pin", "is not the file the spec pins"),
        ("outputs", "does not hold exactly the ruled outputs"),
        ("engine", "is not a 2026-11-01 developer record"),
        ("decided_on", "is not a 2026-11-01 developer record"),
        ("decided_by", "is not a 2026-11-01 developer record"),
        ("two", "expected 1 records"),
        ("excluded", "a ruled output is already excluded"),
    ],
)
def test_the_driver_refuses_any_record_but_the_ruled_one(
    tmp_path, monkeypatch, case, message
):
    edits = {
        "engine": lambda r: r.update(engine_version="policyengine-us 2.38.6"),
        "decided_on": lambda r: r.update(decided_on="2026-10-31"),
        "decided_by": lambda r: r.update(decided_by="judge"),
    }
    extra = [_another_record()] if case == "two" else []
    outputs = None
    if case == "outputs":
        outputs = [["scenario_122", "snap"]]
    elif case == "two":
        outputs = [list(RULED), ["scenario_000", "snap"]]
    elif case == "excluded":
        edits["excluded"] = lambda r: r.update(
            scenario_id="scenario_023", variable="snap"
        )
        outputs = [["scenario_023", "snap"]]
    spec = proposal_spec(
        tmp_path, monkeypatch, edit=edits.get(case), extra=extra, outputs=outputs
    )
    if case == "pin":
        spec["proposals"][0]["sha256"] = "0" * 64
    with pytest.raises(SystemExit, match=message):
        driver.build_release_exclusions(base_record(), spec)


def test_the_derivation_takes_its_sentence_once_before_its_marker():
    spec = real_spec()
    spec["derivation_insert"] = {**spec["derivation_insert"], "before": " no marker"}
    with pytest.raises(SystemExit, match="marker exactly once"):
        driver.build_release_exclusions(driver.base_exclusion_record(), spec)


# The two mutations of the ruled record find it by its key. By position,
# add_another_output followed by drop_the_ruled_record dropped the added
# record instead, and the mutated record matched the release's.
def _drop_the_ruled_record(doc: dict) -> None:
    doc["exclusions"] = [
        record for record in doc["exclusions"] if driver.spec_key(record) != RULED
    ]


def _edit_the_ruled_value(doc: dict) -> None:
    for record in doc["exclusions"]:
        if driver.spec_key(record) == RULED:
            record.update(alternative_value=1920.0)


RECORD_MUTATIONS = {
    "drop_a_base_record": lambda d: d["exclusions"].pop(0),
    "drop_the_ruled_record": _drop_the_ruled_record,
    "edit_a_base_note": lambda d: d["exclusions"][3].update(note="edited"),
    "edit_the_ruled_value": _edit_the_ruled_value,
    "add_another_output": lambda d: d["exclusions"].insert(-1, _another_record()),
    "reorder": lambda d: d["exclusions"].reverse(),
    "edit_the_derivation": lambda d: d.update(derivation=d["derivation"] + " "),
}


@settings(max_examples=30, deadline=None)
@given(
    names=st.lists(
        st.sampled_from(sorted(RECORD_MUTATIONS)), min_size=1, max_size=3, unique=True
    )
)
@example(names=["add_another_output", "drop_the_ruled_record"])
@example(names=["add_another_output", "edit_the_ruled_value", "drop_the_ruled_record"])
def test_a_record_that_differs_from_the_releases_is_refused_at_later_steps(
    pinned_directory, names
):
    doc = release_record()
    for name in names:
        RECORD_MUTATIONS[name](doc)
    assert driver.exclusions_text(doc) != release_text(), names
    path = pinned_directory / EXCLUSIONS_NAME
    original = path.read_bytes()
    release = driver.release_exclusions_sha256()
    try:
        path.write_text(driver.exclusions_text(doc))
        with pytest.raises(
            SystemExit, match="reference_exclusions.json does not match"
        ):
            driver.verify_reference_pins(pinned_directory, "staged reference", release)
    finally:
        path.write_bytes(original)


# --- Installing the record, and the steps that need it ------------------------


@pytest.fixture
def stage(tmp_path):
    """A MOCK prepared stage: release 20261027's references staged and bound."""
    stage = tmp_path / "stage"
    base_references(stage / "scoring")
    us = base_references(stage / "publish" / RUN / "us")
    driver.write_json(
        stage / "stage.json",
        {"partial": False, "early": False, "files": {BOUND: sha(us / EXCLUSIONS_NAME)}},
    )
    return stage


def _files(root: Path) -> dict:
    return {str(p): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def test_install_binds_the_release_record_and_is_idempotent(stage, capsys):
    args = SimpleNamespace(stage_dir=stage)
    driver.install_exclusions(args)
    text = release_text().encode()
    assert (stage / "scoring" / EXCLUSIONS_NAME).read_bytes() == text
    assert (stage / BOUND).read_bytes() == text
    receipt = json.loads((stage / "stage.json").read_text())
    assert receipt["files"] == {BOUND: RELEASE_EXCLUSIONS_SHA256}
    assert receipt["exclusions_installed"] == {
        "base_sha256": driver.BASE_REFERENCE_SHA256[EXCLUSIONS_NAME],
        "sha256": RELEASE_EXCLUSIONS_SHA256,
        "spec_sha256": sha(REPO / driver.SPEC_PATH),
        "records": 50,
    }
    assert "Installed 50 exclusions (1 new)" in capsys.readouterr().out
    # Every other staged reference keeps release 20261027's bytes.
    driver.verify_reference_pins(
        stage / "scoring", "staged scoring", RELEASE_EXCLUSIONS_SHA256
    )
    before = _files(stage)
    driver.install_exclusions(args)
    assert _files(stage) == before


@pytest.mark.parametrize(
    "receipt, message",
    [
        ({"files": {}}, "does not bind the exclusions"),
        ({"files": {BOUND: "0" * 64}}, "is not release 20261027's"),
        ({"references_installed": {"sha256": {}}}, "installed reference build"),
    ],
)
def test_install_refuses_a_stage_this_driver_did_not_prepare(stage, receipt, message):
    path = stage / "stage.json"
    driver.write_json(path, {**json.loads(path.read_text()), **receipt})
    before = _files(stage)
    with pytest.raises(SystemExit, match=message):
        driver.install_exclusions(SimpleNamespace(stage_dir=stage))
    assert _files(stage) == before


@pytest.mark.parametrize("marker", driver.INSTALL_MARKERS)
def test_a_stage_holding_an_installed_builds_files_is_refused(stage, marker):
    (stage / marker).mkdir()
    with pytest.raises(SystemExit, match="installed reference build"):
        driver.stage_upgrade(stage)


@pytest.mark.parametrize("value", [True, {"sha256": {}}, ["build"], "yes"])
def test_a_stage_recording_an_installed_build_is_refused(stage, value):
    path = stage / "stage.json"
    driver.write_json(
        path, {**json.loads(path.read_text()), "references_installed": value}
    )
    with pytest.raises(SystemExit, match="installed reference build"):
        driver.stage_upgrade(stage)


def test_stage_upgrade_regates_the_base_engine_and_publication_record(
    stage, monkeypatch
):
    calls = []
    monkeypatch.setattr(driver, "verify_base_engine", lambda: calls.append("engine"))
    monkeypatch.setattr(
        driver, "verify_publication_record", lambda: calls.append("publication")
    )
    assert driver.stage_upgrade(stage) is None
    assert calls == ["engine", "publication"]
    with pytest.raises(SystemExit, match="lacks stage.json"):
        driver.stage_upgrade(stage / "scoring")


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    """A synthetic checkout root holding copies of the spec and its proposal.

    The base-engine and publication-record gates read this checkout's files
    (tested above); here they record each call instead. The base's record is
    the one the driver read from git before the root moved."""
    root = tmp_path / "workspace"
    for relative in (driver.SPEC_PATH, Path("docs/fable52/proposed_exclusions.json")):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, root / relative)
    monkeypatch.setattr(driver, "ROOT", root)
    monkeypatch.setattr(driver, "base_exclusion_record", base_record)
    monkeypatch.setattr(driver, "SEED_DIGEST", root / "docs/fable52/seed_digest.csv")
    calls = []
    monkeypatch.setattr(driver, "verify_base_engine", lambda: calls.append("engine"))
    monkeypatch.setattr(
        driver, "verify_publication_record", lambda: calls.append("publication")
    )
    return SimpleNamespace(root=root, stage=root / "results/local/stage", calls=calls)


STEP_FUNCTIONS = {
    "bind-seed": "bind_seed",
    "install-exclusions": "install_exclusions",
    "judge": "judge",
    "adjudicate-exclusions": "adjudicate_exclusions",
    "provenance": "write_judge_provenance",
    "triage": "triage",
    "export": "export_stage",
}
GATED_STEPS = [
    s for s in STEP_FUNCTIONS if s not in ("bind-seed", "install-exclusions")
]


def _record_steps(monkeypatch) -> list[str]:
    calls = []
    for name in STEP_FUNCTIONS.values():
        monkeypatch.setattr(driver, name, lambda *a, n=name: calls.append(n))
    return calls


EXPLANATIONS_PATH = Path("annotations") / RUN / "us_case_reference_explanations.csv"


def _resumable(stage: Path, **receipt) -> None:
    """A prepared release stage as main's later steps find it (MOCK run
    files): release 20261027's references in the scoring source and the
    bundle, the release's exclusion record in both where ``receipt`` records
    it installed; the base's explanations; the new model's run files and
    their model-provenance.json entry; and stage.json naming every prepared
    input (review r1, M7)."""
    bundle = stage / "publish" / RUN
    installed = receipt.get("exclusions_installed")
    for directory in (stage / "scoring", bundle / "us"):
        base_references(directory)
        if (installed or {}).get("sha256") == RELEASE_EXCLUSIONS_SHA256:
            (directory / EXCLUSIONS_NAME).write_text(release_text())
    (bundle / "us/predictions.csv").write_text("model,scenario_id,variable\n")
    annotations = bundle / "annotations"
    annotations.mkdir(parents=True)
    (annotations / EXPLANATIONS_PATH.name).write_bytes(base_blob(EXPLANATIONS_PATH))
    inputs = stage / "inputs" / SLUG
    inputs.mkdir(parents=True)
    (inputs / "predictions.csv").write_text("MOCK run rows\n")
    fingerprint = {"MOCK": "treatment"}
    driver.write_json(
        inputs / "run_state.json", {"model": NEW, "treatment_fingerprint": fingerprint}
    )
    driver.write_json(
        stage / "model-provenance.json",
        {
            NEW: {
                "predictions_sha256": sha(inputs / "predictions.csv"),
                "treatment_fingerprint": fingerprint,
            }
        },
    )
    names = [inputs / name for name in driver.PINNED_INPUTS]
    names += [bundle / "us" / n for n in (*driver.REFERENCE_FILES, "predictions.csv")]
    files = {str(path.relative_to(stage)): sha(path) for path in names}
    driver.write_json(
        stage / "stage.json",
        {"partial": False, "early": False, "files": files, **receipt},
    )


def _main_step(workspace, step) -> None:
    driver.main(["--stage-dir", str(workspace.stage), "--step", step])


def _restamp(stage: Path, path: Path) -> None:
    """stage.json follows ``path``, as an edit made to pass its check would."""
    receipt = json.loads((stage / "stage.json").read_text())
    receipt["files"][str(path.relative_to(stage))] = sha(path)
    driver.write_json(stage / "stage.json", receipt)


@pytest.mark.parametrize("step", GATED_STEPS)
@pytest.mark.parametrize(
    "installed",
    [
        None,
        {},
        {"sha256": driver.BASE_REFERENCE_SHA256[EXCLUSIONS_NAME]},
        {"sha256": "0" * 64},
    ],
)
def test_later_steps_refuse_a_stage_without_the_release_record(
    workspace, monkeypatch, step, installed
):
    calls = _record_steps(monkeypatch)
    receipt = {} if installed is None else {"exclusions_installed": installed}
    _resumable(workspace.stage, **receipt)
    with pytest.raises(SystemExit, match="exclusions are not the release's"):
        driver.main(["--stage-dir", str(workspace.stage), "--step", step])
    assert calls == []


@pytest.mark.parametrize("step", GATED_STEPS)
def test_a_stage_with_the_release_record_reaches_its_step(workspace, monkeypatch, step):
    calls = _record_steps(monkeypatch)
    _resumable(
        workspace.stage, exclusions_installed={"sha256": RELEASE_EXCLUSIONS_SHA256}
    )
    driver.main(["--stage-dir", str(workspace.stage), "--step", step])
    assert calls == [STEP_FUNCTIONS[step]]
    assert workspace.calls == ["engine", "publication"]


@pytest.mark.parametrize("step", ["bind-seed", "install-exclusions"])
def test_the_steps_that_bind_or_install_run_before_the_record(
    workspace, monkeypatch, step
):
    calls = _record_steps(monkeypatch)
    _resumable(workspace.stage)
    driver.main(["--stage-dir", str(workspace.stage), "--step", step])
    assert calls == [STEP_FUNCTIONS[step]]


@pytest.mark.parametrize("step", STEP_FUNCTIONS)
def test_a_staged_record_edited_after_install_stops_every_step(
    workspace, monkeypatch, step
):
    calls = _record_steps(monkeypatch)
    _resumable(
        workspace.stage, exclusions_installed={"sha256": RELEASE_EXCLUSIONS_SHA256}
    )
    record = workspace.stage / BOUND
    assert record.read_text() == release_text()
    record.write_text(release_text().replace("Certificate", "certificate", 1))
    with pytest.raises(SystemExit, match=f"staged input changed: {re.escape(BOUND)}"):
        driver.main(["--stage-dir", str(workspace.stage), "--step", step])
    assert calls == []


# Review r1, M7: what every later step checks of the prepared stage, before
# its step runs, beyond stage.json's own hashes (which move with it).

INSTALLED = {"exclusions_installed": {"sha256": RELEASE_EXCLUSIONS_SHA256}}


@pytest.mark.parametrize("step", STEP_FUNCTIONS)
@pytest.mark.parametrize(
    "dropped",
    ["all", f"inputs/{SLUG}/run_state.json", f"publish/{RUN}/us/{driver.CSV_NAME}"],
)
def test_every_later_step_refuses_a_stage_json_naming_too_few_inputs(
    workspace, monkeypatch, step, dropped
):
    """A stage.json with no files (as the old later-step tests built one), or
    without one prepared input, stops every later step: before M7 only export
    required the set."""
    calls = _record_steps(monkeypatch)
    _resumable(workspace.stage, **INSTALLED)
    receipt = json.loads((workspace.stage / "stage.json").read_text())
    if dropped == "all":
        receipt["files"] = {}
    else:
        del receipt["files"][dropped]
    driver.write_json(workspace.stage / "stage.json", receipt)
    with pytest.raises(SystemExit, match="stage.json does not record"):
        _main_step(workspace, step)
    assert calls == []


@pytest.mark.parametrize("step", STEP_FUNCTIONS)
def test_every_later_step_rechecks_the_model_provenance(workspace, monkeypatch, step):
    calls = _record_steps(monkeypatch)
    _resumable(workspace.stage, **INSTALLED)
    path = workspace.stage / "model-provenance.json"
    record = json.loads(path.read_text())
    record[NEW]["predictions_sha256"] = "0" * 64
    driver.write_json(path, record)
    with pytest.raises(SystemExit, match="model-provenance.json disagrees"):
        _main_step(workspace, step)
    assert calls == []


@pytest.mark.parametrize("step", STEP_FUNCTIONS)
@pytest.mark.parametrize("where", ["scoring", "bundle"])
@pytest.mark.parametrize("name", driver.REFERENCE_FILES)
def test_every_later_step_holds_the_staged_references_to_their_pins(
    workspace, monkeypatch, step, where, name
):
    """A staged reference one byte off its code-held pin stops every later
    step: in the scoring source, which stage.json does not bind, or in the
    bundle with stage.json following the edit."""
    calls = _record_steps(monkeypatch)
    _resumable(workspace.stage, **INSTALLED)
    directory = "scoring" if where == "scoring" else f"publish/{RUN}/us"
    path = workspace.stage / directory / name
    path.write_bytes(path.read_bytes() + b"\n")
    if where == "bundle":
        _restamp(workspace.stage, path)
    label = "staged scoring" if where == "scoring" else "staged reference"
    with pytest.raises(SystemExit, match=f"{label} {re.escape(name)} does not match"):
        _main_step(workspace, step)
    assert calls == []


@pytest.mark.parametrize("step", ["bind-seed", "install-exclusions"])
@pytest.mark.parametrize("record", ["release", "release_edited", "edited"])
def test_before_the_install_the_staged_record_is_the_bases(
    workspace, monkeypatch, step, record
):
    """Until install-exclusions records the release's record, the pin is
    release 20261027's: the base's record edited, or the release's edited,
    in the scoring source stops either step, and the release's record there
    stops bind-seed. Review r2, N3: install-exclusions takes the release's
    exact record there, the state an install stopped after its first write
    leaves (tested below)."""
    calls = _record_steps(monkeypatch)
    _resumable(workspace.stage)
    path = workspace.stage / "scoring" / EXCLUSIONS_NAME
    if record == "release":
        path.write_text(release_text())
    elif record == "release_edited":
        path.write_text(release_text() + "\n")
    else:
        path.write_bytes(path.read_bytes() + b"\n")
    if (step, record) == ("install-exclusions", "release"):
        _main_step(workspace, step)
        assert calls == ["install_exclusions"]
        return
    with pytest.raises(
        SystemExit, match=f"staged scoring {EXCLUSIONS_NAME} does not match its pin"
    ):
        _main_step(workspace, step)
    assert calls == []


def _stop_at_the_bundle_copy(monkeypatch) -> None:
    """MOCK: writing the bundle's exclusion record fails, as a full disk
    would; every other write goes through."""
    write_text = Path.write_text

    def write(path, *args, **kwargs):
        if path.name == EXCLUSIONS_NAME and path.parent.name == "us":
            raise OSError("MOCK: no space left on device")
        return write_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write)


def test_an_install_stopped_after_its_first_write_can_be_run_again(
    workspace, monkeypatch
):
    """Review r2, N3 (G P3-1): an install stopped between its two writes
    leaves the release's record in the scoring source, release 20261027's in
    the bundle and no install recorded. The step run again passes main's
    pins, writes both copies and records the install, and the next step's
    pins pass. Before N3 the rerun stopped at the scoring copy's pin."""
    _resumable(workspace.stage)
    scoring = workspace.stage / "scoring" / EXCLUSIONS_NAME
    bundle = workspace.stage / BOUND
    with monkeypatch.context() as patch:
        _stop_at_the_bundle_copy(patch)
        with pytest.raises(OSError, match="MOCK: no space left"):
            _main_step(workspace, "install-exclusions")
    assert scoring.read_text() == release_text()
    assert bundle.read_bytes() == base_blob(SNAPSHOT_PATH / EXCLUSIONS_NAME)
    receipt = json.loads((workspace.stage / "stage.json").read_text())
    assert "exclusions_installed" not in receipt
    _main_step(workspace, "install-exclusions")
    assert scoring.read_text() == bundle.read_text() == release_text()
    receipt = json.loads((workspace.stage / "stage.json").read_text())
    assert receipt["exclusions_installed"]["sha256"] == RELEASE_EXCLUSIONS_SHA256
    assert receipt["files"][BOUND] == RELEASE_EXCLUSIONS_SHA256
    calls = _record_steps(monkeypatch)
    _main_step(workspace, "judge")
    assert calls == ["judge"]


@pytest.mark.parametrize("edit", ["bundle", "bound_bundle", "scoring_reference"])
def test_a_half_written_install_takes_no_other_byte_state(workspace, monkeypatch, edit):
    """Beside the half-written install's scoring copy, the bundle copy must
    still be release 20261027's bound bytes and every other scoring
    reference its pin: an edit to either stops the rerun before it writes.
    The release's record in the bundle stops it whether or not stage.json
    follows the edit (an install stopped after both writes leaves the
    first; "prepare a new stage" recovers it)."""
    _resumable(workspace.stage)
    with monkeypatch.context() as patch:
        _stop_at_the_bundle_copy(patch)
        with pytest.raises(OSError, match="MOCK: no space left"):
            _main_step(workspace, "install-exclusions")
    if edit == "bundle":
        (workspace.stage / BOUND).write_text(release_text())
        message = "staged input changed"
    elif edit == "bound_bundle":
        (workspace.stage / BOUND).write_text(release_text())
        _restamp(workspace.stage, workspace.stage / BOUND)
        message = f"staged reference {EXCLUSIONS_NAME} does not match its pin"
    else:
        path = workspace.stage / "scoring" / driver.CSV_NAME
        path.write_bytes(path.read_bytes() + b"\n")
        message = f"staged scoring {driver.CSV_NAME} does not match its pin"
    calls = _record_steps(monkeypatch)
    before = _files(workspace.stage)
    with pytest.raises(SystemExit, match=message):
        _main_step(workspace, "install-exclusions")
    assert calls == []
    assert _files(workspace.stage) == before


STOPPED_REINSTALL = (
    f"staged scoring {EXCLUSIONS_NAME} is neither the record this stage recorded "
    "installing nor a first install's, since the stage records an install; a "
    "reinstall stopped between its writes leaves this; prepare a new stage"
)


def _installed_earlier(workspace) -> str:
    """MOCK: the stage records an install of an earlier spec's record, whose
    bytes both copies hold and stage.json binds; return them."""
    earlier = release_text() + "MOCK earlier record\n"
    _resumable(
        workspace.stage,
        exclusions_installed={"sha256": hashlib.sha256(earlier.encode()).hexdigest()},
    )
    for directory in ("scoring", f"publish/{RUN}/us"):
        (workspace.stage / directory / EXCLUSIONS_NAME).write_text(earlier)
    _restamp(workspace.stage, workspace.stage / BOUND)
    return earlier


def test_a_stopped_reinstall_is_still_refused(workspace, monkeypatch):
    """N3 accepts the release's record in the scoring copy only where no
    install is recorded, as review r2 ruled. A reinstall, which later steps
    ask for when the spec's record no longer matches the one installed,
    stopped between its writes leaves the release's record in the scoring
    copy beside the earlier record stage.json binds (MOCK bytes here): the
    rerun stops before any step runs, as before N3. The coordinator's ruling
    keeps the refusal and has its message name the recovery."""
    _installed_earlier(workspace)
    (workspace.stage / "scoring" / EXCLUSIONS_NAME).write_text(release_text())
    calls = _record_steps(monkeypatch)
    with pytest.raises(SystemExit, match=re.escape(STOPPED_REINSTALL)):
        _main_step(workspace, "install-exclusions")
    assert calls == []


@pytest.mark.parametrize(
    "held, message",
    [
        ("recorded", None),
        ("release", re.escape(STOPPED_REINSTALL)),
        ("base", f"staged scoring {EXCLUSIONS_NAME} does not match its pin"),
        ("recorded_edited", f"staged scoring {EXCLUSIONS_NAME} does not match its pin"),
    ],
    ids=["recorded", "release", "base", "recorded_edited"],
)
def test_a_reinstall_takes_exactly_the_record_it_recorded(
    workspace, monkeypatch, held, message
):
    """With an install recorded, install-exclusions takes the scoring copy's
    record only when it is the one recorded: the ruling's message changed
    which words a refusal uses, not which states pass."""
    earlier = _installed_earlier(workspace)
    path = workspace.stage / "scoring" / EXCLUSIONS_NAME
    if held == "release":
        path.write_text(release_text())
    elif held == "base":
        path.write_bytes(base_blob(SNAPSHOT_PATH / EXCLUSIONS_NAME))
    elif held == "recorded_edited":
        path.write_text(earlier + "\n")
    calls = _record_steps(monkeypatch)
    if message is None:
        _main_step(workspace, "install-exclusions")
        assert calls == ["install_exclusions"]
        return
    with pytest.raises(SystemExit, match=message):
        _main_step(workspace, "install-exclusions")
    assert calls == []


def test_a_reinstall_holds_the_record_to_the_one_the_stage_installed(
    workspace, monkeypatch
):
    """install-exclusions run again finds the record it installed, as
    stage.json records it, in both copies."""
    calls = _record_steps(monkeypatch)
    _resumable(workspace.stage, **INSTALLED)
    _main_step(workspace, "install-exclusions")
    assert calls == ["install_exclusions"]
    path = workspace.stage / "scoring" / EXCLUSIONS_NAME
    path.write_bytes(base_blob(SNAPSHOT_PATH / EXCLUSIONS_NAME))
    with pytest.raises(SystemExit, match="staged scoring reference_exclusions"):
        _main_step(workspace, "install-exclusions")
    assert calls == ["install_exclusions"]


@pytest.mark.parametrize("step", STEP_FUNCTIONS)
@pytest.mark.parametrize("defect", ["edited", "missing"])
def test_every_later_step_holds_the_explanations_to_the_base(
    workspace, monkeypatch, step, defect
):
    """stage.json does not bind the explanations; every later step holds
    them to release 20261027's bytes."""
    calls = _record_steps(monkeypatch)
    _resumable(workspace.stage, **INSTALLED)
    path = workspace.stage / f"publish/{RUN}/annotations" / EXPLANATIONS_PATH.name
    if defect == "edited":
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        path.unlink()
    with pytest.raises(SystemExit, match="rewords no reference explanation"):
        _main_step(workspace, step)
    assert calls == []


def _prepare_mocks(workspace, monkeypatch, explanations=None) -> dict:
    """discover_new_models, resolve_base, prepare_inputs and export mocked:
    prepare_inputs stages release 20261027's references (MOCK runs) and its
    explanations, or ``explanations`` as a stopped prepare could have left
    them."""
    stage, seen = workspace.stage, {}
    monkeypatch.setattr(driver, "discover_new_models", lambda root: [])
    monkeypatch.setattr(
        driver, "resolve_base", lambda args: (None, None, {"countries": {}})
    )

    def prepared(args, runs, base, reference):
        base_references(stage / "scoring")
        bundle = stage / "publish" / RUN
        base_references(bundle / "us")
        (bundle / "us/predictions.csv").write_text("model,scenario_id,variable\n")
        (stage / "inputs" / SLUG).mkdir(parents=True)
        (stage / "inputs" / SLUG / "predictions.csv").write_text("MOCK\n")
        (bundle / "annotations").mkdir()
        (bundle / "annotations" / EXPLANATIONS_PATH.name).write_bytes(
            base_blob(EXPLANATIONS_PATH) if explanations is None else explanations
        )
        return bundle, {}

    def exported(args, bundle, live):
        seen["receipt"] = json.loads((stage / "stage.json").read_text())
        seen["records"] = [
            (stage / where / EXCLUSIONS_NAME).read_bytes()
            for where in ("scoring", f"publish/{RUN}/us")
        ]

    monkeypatch.setattr(driver, "prepare_inputs", prepared)
    monkeypatch.setattr(driver, "export", exported)
    return seen


def test_an_early_rehearsal_scores_the_release_record_and_can_never_release(
    workspace, monkeypatch
):
    seen = _prepare_mocks(workspace, monkeypatch)
    runs = workspace.root / "runs"
    driver.main(
        ["--stage-dir", str(workspace.stage), "--step", "prepare", "--early"]
        + ["--runs-root", str(runs)]
    )
    installed = {
        "base_sha256": driver.BASE_REFERENCE_SHA256[EXCLUSIONS_NAME],
        "sha256": RELEASE_EXCLUSIONS_SHA256,
        "spec_sha256": sha(REPO / driver.SPEC_PATH),
        "records": 50,
    }
    assert seen["receipt"] == {
        "early": True,
        "partial": False,
        "files": {},
        "exclusions_installed": installed,
    }
    assert seen["records"] == [release_text().encode()] * 2
    receipt = json.loads((workspace.stage / "stage.json").read_text())
    assert (receipt["early"], receipt["partial"]) == (True, False)
    assert receipt["exclusions_installed"] == installed
    assert receipt["files"][BOUND] == RELEASE_EXCLUSIONS_SHA256
    assert workspace.calls == ["engine", "publication"]
    with pytest.raises(SystemExit, match="cannot become a release"):
        driver.require_release_stage(receipt)


def test_prepare_checks_the_base_engine_and_publication_record_before_writing(
    workspace, monkeypatch
):
    _prepare_mocks(workspace, monkeypatch)

    def refused():
        raise SystemExit("the audit's publication record disagrees (MOCK)")

    monkeypatch.setattr(driver, "verify_publication_record", refused)
    with pytest.raises(SystemExit, match="publication record disagrees"):
        driver.main(
            ["--stage-dir", str(workspace.stage), "--step", "prepare"]
            + ["--runs-root", str(workspace.root / "runs")]
        )
    assert not workspace.stage.exists()


@pytest.mark.parametrize("mode", [[], ["--early"]], ids=["release", "early"])
def test_prepare_refuses_edited_explanations_before_a_prompt_renders(
    workspace, monkeypatch, mode
):
    """Review r1, M7 (D's case 2): prepare_inputs keeps the explanations a
    stopped prepare left in the bundle. An edited copy stops prepare right
    after prepare_inputs: before prepare_cases renders a judge prompt from
    it, before an early rehearsal exports it, and before stage.json."""
    seen = _prepare_mocks(workspace, monkeypatch, explanations=b"MOCK edited\n")
    monkeypatch.setattr(
        driver, "prepare_cases", lambda *a: pytest.fail("prepare_cases ran")
    )
    with pytest.raises(SystemExit, match="rewords no reference explanation"):
        driver.main(
            ["--stage-dir", str(workspace.stage), "--step", "prepare", *mode]
            + ["--runs-root", str(workspace.root / "runs")]
        )
    assert seen == {}
    assert not (workspace.stage / "stage.json").exists()


def test_prepare_passes_the_bases_explanations_to_prepare_cases(workspace, monkeypatch):
    _prepare_mocks(workspace, monkeypatch)
    rendered = []
    monkeypatch.setattr(
        driver, "prepare_cases", lambda args, bundle: rendered.append(bundle) or {}
    )
    driver.main(
        ["--stage-dir", str(workspace.stage), "--step", "prepare"]
        + ["--runs-root", str(workspace.root / "runs")]
    )
    assert rendered == [workspace.stage / "publish" / RUN]


@pytest.fixture
def seed_audit(tmp_path, monkeypatch):
    """A MOCK judged seed and grounding, pinned in place of the real ones."""
    seed = tmp_path / "seed"
    for index in range(3):
        case = seed / "cases" / f"us__s{index}__snap"
        case.mkdir(parents=True)
        (case / "prompt.md").write_text(f"MOCK prompt {index}\n")
        (case / "verdict.json").write_text(json.dumps({"MOCK": index}))
    digest_text = driver.seed_digest_text(driver.seed_digest(seed))
    monkeypatch.setattr(driver, "SEED_DIGEST_SHA256", sha(digest_text.encode()))
    grounding = tmp_path / "grounding.csv"
    grounding.write_text("scenario_id,variable,grounding\n")
    monkeypatch.setattr(driver, "GROUNDING_SHA256", sha(grounding))
    return seed, grounding


def test_bind_seed_before_prepare_checks_the_seed_and_writes_nothing(
    workspace, seed_audit, capsys
):
    seed, grounding = seed_audit
    before = sorted(workspace.root.rglob("*"))
    driver.main(
        ["--stage-dir", str(workspace.stage), "--step", "bind-seed"]
        + ["--audit-seed", str(seed), "--grounding", str(grounding)]
    )
    assert "3 judged cases; prepare binds it" in capsys.readouterr().out
    assert sorted(workspace.root.rglob("*")) == before
    assert not workspace.stage.exists()


@pytest.mark.parametrize(
    "defect, message",
    [
        ("verdict", "is not release 20261027's"),
        ("unjudged", "seed case unjudged"),
        ("grounding", "grounding differs"),
        ("no_seed", "bind-seed needs --audit-seed"),
    ],
)
def test_bind_seed_before_prepare_refuses_another_seed_or_grounding(
    seed_audit, defect, message
):
    seed, grounding = seed_audit
    if defect == "verdict":
        (seed / "cases/us__s0__snap/verdict.json").write_text("{}")
    elif defect == "unjudged":
        (seed / "cases/us__s1__snap/verdict.json").unlink()
    elif defect == "grounding":
        grounding.write_text(grounding.read_text() + "s0,snap,MOCK\n")
    args = SimpleNamespace(
        audit_seed=None if defect == "no_seed" else seed, grounding=grounding
    )
    with pytest.raises(SystemExit, match=message):
        driver.check_seed(args)


# --- Export's scope check, with a mocked exporter ------------------------------

FABLE_USAGE = {
    "costUsd": 54.0,
    "costPerHousehold": 0.54,
    "totalTokens": 3850174,
    "latencySeconds": 97.5,
}


def stat(model, exact=50.0, n=1934, **usage):
    return {
        "model": model,
        "condition": "no_tools",
        "score": exact / 100,
        "exact": exact,
        "n": n,
        **usage,
    }


def incumbents(n=1935):
    """Release 20261027's 51 MOCK incumbents, Fable 5 last."""
    return (
        [stat(f"incumbent-{i:02d}", n=n, costUsd=1.25) for i in range(49)]
        + [stat("ox-alpha", n=n, costUsd=0.0, costPerHousehold=0.0)]
        + [stat("claude-fable-5", n=n, **FABLE_USAGE)]
    )


@pytest.fixture
def scope(tmp_path, monkeypatch):
    """export_full_run, the scope export, exclusion_scope_problems and the
    dashboard validator mocked (MOCK stats). The bundle holds release
    20261027's references and the release's record, as install leaves it."""
    import policybench.dashboard_schema
    import policybench.full_run_export

    bundle = tmp_path / "scope-bundle"
    base_references(bundle / "us")
    (bundle / "us" / EXCLUSIONS_NAME).write_text(release_text())
    (bundle / "us/predictions.csv").write_text("model,scenario_id,variable\n")
    (bundle / "annotations").mkdir()
    for name in release_20261006.ANNOTATION_CSVS:
        (bundle / "annotations" / name).write_text("country\n")
    state = SimpleNamespace(records=[], options=[], ruled=[], problems=[])

    def exported(path, **kw):
        path = Path(path)
        payload = {"countries": {"us": {"modelStats": copy.deepcopy(state.stats)}}}
        (path / "us/analysis").mkdir(parents=True, exist_ok=True)
        (path / "us/analysis/summary.csv").write_text("MOCK analysis\n")
        (path / "us/data.json").write_text(json.dumps(payload["countries"]["us"]))
        (path / "data.json").write_text(json.dumps(payload))
        return payload

    def scoped(path, live, record=None, **options):
        state.records.append(Path(record).read_bytes())
        state.options.append(options)
        return {"countries": {"us": {"modelStats": copy.deepcopy(state.base_stats)}}}

    def problems(payload, scoped_payload, records, limit=8):
        state.ruled.append([driver.spec_key(record) for record in records])
        return list(state.problems)

    monkeypatch.setattr(policybench.full_run_export, "export_full_run", exported)
    monkeypatch.setattr(release_20261006, "export_payload", scoped)
    monkeypatch.setattr(driver, "exclusion_scope_problems", problems)
    monkeypatch.setattr(
        policybench.dashboard_schema, "validate_dashboard_payload", lambda *a, **k: []
    )

    def build(previous=None, early=False):
        previous = incumbents() if previous is None else previous
        live = {"countries": {"us": {"modelStats": previous}}}
        return driver.build_payload(bundle, live, early=early)

    state.build, state.bundle = build, bundle
    # The scope export puts the base's record back: every incumbent is the
    # base's, and the new model is scored on the ruled output too.
    state.base_stats = incumbents() + [stat(NEW, n=1935)]
    state.stats = [
        dict(row, n=1934, exact=row["exact"] + 0.25) for row in incumbents()
    ] + [stat(NEW)]
    for key in FABLE_USAGE:
        del state.stats[50][key]
    return state


def test_the_scope_export_puts_back_release_20261027s_record(scope):
    payload = scope.build()
    assert len(payload["countries"]["us"]["modelStats"]) == 52
    assert scope.records == [base_blob(SNAPSHOT_PATH / EXCLUSIONS_NAME)]
    assert scope.options == [{"require_failure_annotations": True}]
    assert scope.ruled == [[RULED]]
    assert (scope.bundle / "us" / EXCLUSIONS_NAME).read_text() == release_text()


def test_an_early_rehearsals_scope_export_waives_only_the_failure_annotations(scope):
    scope.build(early=True)
    assert scope.options == [{"require_failure_annotations": False}]
    assert scope.ruled == [[RULED]]


def test_scope_carries_fable_usage_and_keeps_a_known_zero_cost(scope):
    rows = scope.build()["countries"]["us"]["modelStats"]
    fable = next(row for row in rows if row["model"] == "claude-fable-5")
    assert {key: fable[key] for key in FABLE_USAGE} == FABLE_USAGE
    assert next(row for row in rows if row["model"] == "ox-alpha")["costUsd"] == 0.0


@settings(
    max_examples=35,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(target=st.integers(0, 50), delta=st.sampled_from([1e-12, 0.25, 1.0]))
def test_with_the_bases_record_every_incumbent_must_be_byte_identical(
    scope, target, delta
):
    original = copy.deepcopy(scope.base_stats)
    assert len(scope.build()["countries"]["us"]["modelStats"]) == 52
    scope.base_stats[target]["exact"] += delta
    try:
        with pytest.raises(SystemExit, match="incumbent modelStats drift"):
            scope.build()
    finally:
        scope.base_stats = original


def test_export_refuses_a_payload_that_moves_beyond_the_one_excluded_output(scope):
    scope.problems = ["scenario_000 snap changed; no record excludes it"]
    with pytest.raises(SystemExit, match="beyond the ruled outputs"):
        scope.build()


@pytest.mark.parametrize("index", [0, 49, 50, 51])
@pytest.mark.parametrize("n", [1933, 1935])
def test_every_incumbent_and_fable52_are_scored_on_1934_outputs(scope, index, n):
    scope.stats[index]["n"] = n
    with pytest.raises(SystemExit, match="must be scored on 1934 outputs"):
        scope.build()


@pytest.mark.parametrize("staged", ["base", "another"])
def test_a_staged_record_adding_anything_but_the_ruled_output_is_refused(scope, staged):
    doc = base_record() if staged == "base" else release_record()
    if staged == "another":
        doc["exclusions"].insert(-1, _another_record())
    (scope.bundle / "us" / EXCLUSIONS_NAME).write_text(driver.exclusions_text(doc))
    with pytest.raises(SystemExit, match="not the ruled outputs"):
        scope.build()
    assert scope.ruled == []


def test_the_roster_is_the_51_incumbents_plus_fable52(scope):
    scope.stats[51]["model"] = "another-model"
    with pytest.raises(SystemExit, match="incumbents plus the addition"):
        scope.build()
    scope.stats[51]["model"] = NEW
    with pytest.raises(SystemExit, match="51 incumbents only"):
        scope.build(previous=incumbents()[:-1] + [stat(NEW, n=1935)])
    scope.stats.pop()
    with pytest.raises(SystemExit, match="all 52 models"):
        scope.build()


@settings(max_examples=35, deadline=None)
@given(
    rows=st.lists(
        st.one_of(
            st.integers(min_value=-(10**6), max_value=10**6),
            st.floats(allow_nan=False, allow_infinity=False),
        ),
        min_size=1,
        max_size=20,
    ),
    pick=st.integers(min_value=0, max_value=10**6),
)
def test_incumbent_drift_keeps_serialized_types_and_key_order(rows, pick):
    previous = {
        f"m{i}": {"model": f"m{i}", "exact": value, "n": 1935}
        for i, value in enumerate(rows)
    }
    stats = copy.deepcopy(list(previous.values()))
    assert driver.incumbent_drift(stats, previous) == []
    # Review r1, M10 (S P3-4): a value that keeps its number and changes its
    # serialized type. == calls 1935 and 1935.0 equal; json.dumps tells them
    # apart, and so does the check.
    index = pick % len(rows)
    retyped = copy.deepcopy(stats)
    retyped[index]["n"] = float(retyped[index]["n"])
    assert retyped[index] == previous[f"m{index}"]
    assert driver.incumbent_drift(retyped, previous) == [f"m{index}"]
    value = rows[index]
    if isinstance(value, int) or value.is_integer():
        retyped = copy.deepcopy(stats)
        retyped[index]["exact"] = float(value) if isinstance(value, int) else int(value)
        assert retyped[index] == previous[f"m{index}"]
        assert driver.incumbent_drift(retyped, previous) == [f"m{index}"]
    stats[0] = dict(reversed(list(stats[0].items())))
    assert driver.incumbent_drift(stats, previous) == ["m0"]
    assert driver.incumbent_drift(stats[1:], previous) == ["m0"]


# --- Export's scope check on the real exporter: a MOCK three-household board ---
#
# The exporter, the dashboard validator and both scope checks run for real.
# The board holds three households' committed references and scenarios; every
# answer and failure annotation is MOCK DATA.

HOUSEHOLDS = ("scenario_000", "scenario_023", "scenario_122")
MOCK_INCUMBENTS = ("mock-incumbent-a", "mock-incumbent-b")
MOCK_MODELS = (*MOCK_INCUMBENTS, NEW)
KINDS = ("right", "wrong", "missing")
MOVED = ("scored", "excludedReason", "excludedInput")


OTHER = ("scenario_000", "snap")


@functools.cache
def board_references() -> pd.DataFrame:
    # The committed references, which every gate holds to the base's pin.
    reference = pd.read_csv(driver.SNAPSHOT / CSV_NAME)
    return reference[reference.scenario_id.isin(HOUSEHOLDS)].reset_index(drop=True)


def board_row(key: tuple[str, str]) -> int:
    reference = board_references()
    (row,) = reference.index[
        (reference.scenario_id == key[0]) & (reference.variable == key[1])
    ]
    return int(row)


ROWS = len(board_references())
CELLS = ROWS * len(MOCK_MODELS)
RULED_ROW = board_row(RULED)
OTHER_ROW = board_row(OTHER)
# The board's rows the base's record leaves scored.
OPEN_ROWS = [
    row
    for row, key in enumerate(
        zip(board_references().scenario_id, board_references().variable, strict=True)
    )
    if key not in {driver.spec_key(record) for record in BASE_RECORD["exclusions"]}
]


def group_order(reference: pd.DataFrame, doc: dict) -> list[str]:
    """The scored output groups in the order the exporter first meets them.

    The exporter lists each household's prompted outputs, and the weights'
    groups, in this order (build_scenario_prompt_map and
    _output_groups_for_ground_truth in policybench/analysis.py), so an
    exclusion that reorders it changes the payload's scenarios and weights."""
    from policybench.spec import output_group_id

    excluded = {driver.spec_key(record) for record in doc["exclusions"]}
    keys = zip(reference.scenario_id, reference.variable, strict=True)
    return list(
        dict.fromkeys(
            output_group_id(variable)
            for scenario, variable in keys
            if (scenario, variable) not in excluded
        )
    )


def board_docs() -> tuple[dict, dict]:
    """The base's and the release's records, kept to the board's households."""
    docs = []
    for doc in (base_record(), release_record()):
        doc["exclusions"] = [
            r for r in doc["exclusions"] if r["scenario_id"] in HOUSEHOLDS
        ]
        docs.append(doc)
    return docs[0], docs[1]


def is_binary(variable: str) -> bool:
    from policybench.config import BINARY_PROGRAMS
    from policybench.spec import metric_type_for_output

    return metric_type_for_output(variable) == "binary" or variable in BINARY_PROGRAMS


def mock_answer(kind: str, value: float, variable: str) -> float | None:
    if kind == "right":
        return float(value)
    if kind == "missing":
        return None
    if is_binary(variable):
        return 1.0 - float(value)
    return float(value) + max(50.0, abs(float(value)))


def write_board(root: Path, answers: dict, doc: dict, models=MOCK_MODELS) -> Path:
    """A MOCK bundle at ``root``: the households' committed references and
    scenarios, each model's answer of the kind ``answers`` gives (by model and
    row), a failure annotation on every answer that is not right, and ``doc``
    as the exclusion record."""
    if root.exists():
        shutil.rmtree(root)
    us = root / "us"
    us.mkdir(parents=True)
    reference = board_references()
    reference.to_csv(us / CSV_NAME, index=False)
    meta = json.loads(base_blob(SNAPSHOT_PATH / META_NAME))
    meta.update(reference_csv_sha256=sha(us / CSV_NAME), row_count=len(reference))
    (us / META_NAME).write_text(json.dumps(meta))
    scenarios = pd.read_csv(io.BytesIO(base_blob(SNAPSHOT_PATH / "scenarios.csv")))
    scenarios[scenarios.scenario_id.isin(HOUSEHOLDS)].to_csv(
        us / "scenarios.csv", index=False
    )
    (us / "scenarios.csv.meta.json").write_bytes(
        base_blob(SNAPSHOT_PATH / "scenarios.csv.meta.json")
    )
    (us / EXCLUSIONS_NAME).write_text(driver.exclusions_text(doc))
    rows, notes = [], []
    for model in models:
        for index, row in reference.iterrows():
            kind = answers[(model, index)]
            rows.append(
                {
                    "model": model,
                    "scenario_id": row.scenario_id,
                    "variable": row.variable,
                    "prediction": mock_answer(kind, row.value, row.variable),
                    "explanation": "MOCK answer.",
                    "error": None,
                }
            )
            if kind != "right":
                notes.append(
                    {
                        "model": model,
                        "scenario_id": row.scenario_id,
                        "variable": row.variable,
                        "annotation": "MOCK annotation.",
                        "failure_source": (
                            "llm_error" if kind == "wrong" else "parse_contract_failure"
                        ),
                        "failure_subtype": (
                            "thresholds_rates" if kind == "wrong" else "missing_output"
                        ),
                    }
                )
    pd.DataFrame(rows).to_csv(us / "predictions.csv", index=False)
    annotations = root / "annotations"
    annotations.mkdir()
    columns = ["model", "scenario_id", "variable", "annotation"]
    columns += ["failure_source", "failure_subtype"]
    pd.DataFrame(notes, columns=columns).to_csv(
        annotations / "us_audit_row_annotations.csv", index=False
    )
    (annotations / "us_case_notes.csv").write_text(
        "scenario_id,variable,case_annotation,case_failure_sources,"
        "case_failure_subtypes\n"
    )
    explanations = pd.read_csv(
        io.BytesIO(base_blob(ANNOTATIONS_PATH / "us_case_reference_explanations.csv"))
    )
    explanations[explanations.scenario_id.isin(HOUSEHOLDS)].to_csv(
        annotations / "us_case_reference_explanations.csv", index=False
    )
    return root


def export_board(root: Path) -> dict:
    from policybench.full_run_export import export_country

    return {"countries": {"us": export_country(root / "us")}}


def answer_map(kinds) -> dict:
    cells = [(model, index) for model in MOCK_MODELS for index in range(ROWS)]
    return dict(zip(cells, kinds, strict=True))


def mixed_answers() -> dict:
    """MOCK answers of every kind on every MOCK model. On the ruled row the
    MOCK board gives the new model a wrong answer and the MOCK incumbents
    right ones."""
    answers = answer_map(
        KINDS[(index + offset) % 3]
        for offset, _ in enumerate(MOCK_MODELS)
        for index in range(ROWS)
    )
    for model in MOCK_MODELS:
        answers[(model, RULED_ROW)] = "wrong" if model == NEW else "right"
    return answers


def with_a_parsed_answer(answers: dict, doc: dict) -> dict:
    """``answers`` with a parsed answer left in each model's output groups.

    The exporter's heatmap takes each model's mean absolute error over the
    parsed answers of an output group: with none it is NaN, and the
    exporter's JSON dump refuses NaN. A three-household MOCK board leaves a
    group few scored rows, so where a model would parse none of them, the
    group's first scored row answers right (MOCK)."""
    from policybench.spec import output_group_id

    reference = board_references()
    excluded = {driver.spec_key(record) for record in doc["exclusions"]}
    groups: dict[str, list[int]] = {}
    for index, row in reference.iterrows():
        if (row.scenario_id, row.variable) not in excluded:
            groups.setdefault(output_group_id(row.variable), []).append(index)
    kept = dict(answers)
    for model in MOCK_MODELS:
        for rows in groups.values():
            if all(kept[(model, row)] == "missing" for row in rows):
                kept[(model, rows[0])] = "right"
    return kept


@pytest.fixture
def board(tmp_path, monkeypatch):
    """The driver's own export (build_payload) on a MOCK board, its counts
    sized to the board: two incumbents and Fable 5.2, the board's records."""
    base_doc, release_doc = board_docs()
    monkeypatch.setattr(driver, "BASE_MODELS", len(MOCK_INCUMBENTS))
    monkeypatch.setattr(driver, "BOARD_MODELS", len(MOCK_MODELS))
    monkeypatch.setattr(driver, "RELEASE_SCORED", ROWS - len(release_doc["exclusions"]))
    monkeypatch.setattr(driver, "CARRIED_USAGE", {})
    monkeypatch.setattr(release_20261006, "CARRIED_USAGE", {})
    monkeypatch.setattr(
        driver, "base_exclusion_record", lambda: copy.deepcopy(base_doc)
    )
    root = tmp_path / "board"

    def run(
        answers,
        *,
        doc=None,
        base_answers=None,
        edit_base=None,
        reopened=(),
        decided=(),
        annotate=None,
    ):
        """The driver's payload and the base board's export (``edit_base``
        applied to its US country first). ``annotate(directory, side)``, when
        given, edits each board's annotations directory after it is written,
        ``side`` "base" or "release"."""
        written = write_board(
            root / "base", base_answers or answers, base_doc, MOCK_INCUMBENTS
        )
        if annotate is not None:
            annotate(written / "annotations", "base")
        base = export_board(written)
        if edit_base is not None:
            edit_base(base["countries"]["us"])
        bundle = write_board(root / "release", answers, doc or release_doc)
        if annotate is not None:
            annotate(bundle / "annotations", "release")
        payload = driver.build_payload(
            bundle, base, reopened=frozenset(reopened), decided=frozenset(decided)
        )
        return payload, base

    return SimpleNamespace(
        run=run, root=root, base_doc=base_doc, release_doc=release_doc
    )


def test_the_real_exporter_passes_both_scope_checks_on_a_mock_board(board):
    payload, _ = board.run(mixed_answers())
    us = payload["countries"]["us"]
    assert {row["model"]: row["n"] for row in us["modelStats"]} == {
        model: driver.RELEASE_SCORED for model in MOCK_MODELS
    }
    cell = us["scenarioPredictions"][RULED[0]][RULED[1]]
    assert set(cell) == set(MOCK_MODELS)
    assert all(entry["scored"] is False for entry in cell.values())
    assert cell[NEW]["failureSource"] == "llm_error"
    assert [
        (item["scenarioId"], item["variable"]) for item in us["referenceExclusions"]
    ] == [driver.spec_key(record) for record in board.release_doc["exclusions"]]


# Review r1, M9: check (a) holds the rest of what the incumbents share with
# release 20261027. The base here is the real exporter's own export of the
# incumbents' MOCK board, so an unedited base passes (above); each edit makes
# the scope export differ from it where no gate lets it.


def _first_incumbent_cell(us: dict) -> tuple[str, str, str, dict]:
    for scenario in sorted(us["scenarioPredictions"]):
        for variable in sorted(us["scenarioPredictions"][scenario]):
            models = us["scenarioPredictions"][scenario][variable]
            for model in MOCK_INCUMBENTS:
                if model in models:
                    return scenario, variable, model, models[model]
    raise AssertionError("no incumbent cell")


def _edit_heatmap(us: dict) -> str:
    row = next(r for r in us["heatmap"] if r["model"] in MOCK_INCUMBENTS)
    row["score"] += 1
    return f"heatmap {row['model']} {row['variable']} changed"


def _edit_cell(us: dict) -> str:
    scenario, variable, model, cell = _first_incumbent_cell(us)
    cell["prediction"] = (cell["prediction"] or 0) + 1
    return f"scenarioPredictions {scenario} {variable} {model} changed"


def _drop_cell(us: dict) -> str:
    scenario, variable, model, _ = _first_incumbent_cell(us)
    del us["scenarioPredictions"][scenario][variable][model]
    return f"scenarioPredictions {scenario} {variable} {model} changed"


def _reorder_cell(us: dict) -> str:
    scenario, variable, model, cell = _first_incumbent_cell(us)
    reordered = dict(reversed(list(cell.items())))
    us["scenarioPredictions"][scenario][variable][model] = reordered
    return f"scenarioPredictions {scenario} {variable} {model} changed"


def _edit_first_scenario(us: dict) -> str:
    us["scenarios"][sorted(us["scenarios"])[0]]["numAdults"] += 1
    return "scenarios changed"


def _edit_weight(us: dict) -> str:
    weights = us["globalWeights"]["household"]
    weights[sorted(weights)[0]] += 1.0
    return "globalWeights changed"


BASE_EDITS = {
    "country": lambda us: us.update(country="uk") or "country changed",
    "scenarios": _edit_first_scenario,
    "policyengineBundles": lambda us: (
        us["policyengineBundles"].update(MOCK="x") or "policyengineBundles changed"
    ),
    "globalWeights": _edit_weight,
    "referenceExclusions": lambda us: (
        us["referenceExclusions"].append({"scenarioId": "MOCK"})
        or "referenceExclusions changed"
    ),
    "heatmap": _edit_heatmap,
    "cell": _edit_cell,
    "cell_dropped": _drop_cell,
    "cell_key_order": _reorder_cell,
}


@pytest.mark.parametrize("edit", BASE_EDITS)
def test_check_a_refuses_a_base_section_row_or_cell_the_scope_export_lacks(board, edit):
    """Each of the five sections, an incumbent's heatmap row, and an
    incumbent's cell (its value, its presence, its key order) differing
    from the scope export stops the build at check (a)."""
    found = []
    with pytest.raises(SystemExit, match="outside modelStats") as refused:
        board.run(
            mixed_answers(), edit_base=lambda us: found.append(BASE_EDITS[edit](us))
        )
    assert found[0] in str(refused.value)


def _first_board_case(board) -> str:
    payload, _ = board.run(mixed_answers())
    scenario, variable, _, _ = _first_incumbent_cell(payload["countries"]["us"])
    return f"us__{scenario}__{variable}"


# Each annotation field of a cell, and whether check (a) lets it differ on a
# case this release decides and did not re-open (review r2, N1).
DECIDED_MAY_DIFFER = {
    "failureSource": True,
    "failureSubtype": True,
    "caseAnnotation": True,
    "caseFailureSources": True,
    "caseFailureSubtypes": True,
    "annotation": False,
    "referenceExplanation": False,
}


def test_the_fields_a_decision_may_move_are_the_class_fields_and_the_case_note():
    assert set(DECIDED_MAY_DIFFER) == (
        release_20261006.TEXT_CELL_FIELDS | release_20261006.CLASS_CELL_FIELDS
    )
    assert {field for field, may in DECIDED_MAY_DIFFER.items() if may} == (
        release_20261006.CLASS_CELL_FIELDS | {"caseAnnotation"}
    )


@pytest.mark.parametrize("field", DECIDED_MAY_DIFFER)
def test_check_a_lets_annotations_differ_only_on_reopened_and_decided_cases(
    board, field
):
    """An incumbent cell's annotation field that differs from the scope
    export's passes on a case this release re-opened; on a case it decides
    and did not re-open, only the class fields and caseAnnotation pass
    (review r2, N1); on any other case each stops the build. A prediction
    that differs stops it on a re-opened or decided case too."""
    case = _first_board_case(board)

    def annotate(us: dict) -> None:
        _first_incumbent_cell(us)[3][field] = "MOCK: judged again"

    def predict(us: dict) -> None:
        cell = _first_incumbent_cell(us)[3]
        cell["prediction"] = (cell["prediction"] or 0) + 1

    board.run(mixed_answers(), edit_base=annotate, reopened=[case])
    board.run(mixed_answers(), edit_base=annotate, reopened=[case], decided=[case])
    if DECIDED_MAY_DIFFER[field]:
        board.run(mixed_answers(), edit_base=annotate, decided=[case])
    else:
        with pytest.raises(SystemExit, match="outside modelStats"):
            board.run(mixed_answers(), edit_base=annotate, decided=[case])
    with pytest.raises(SystemExit, match="outside modelStats"):
        board.run(mixed_answers(), edit_base=annotate)
    with pytest.raises(SystemExit, match="outside modelStats"):
        board.run(mixed_answers(), edit_base=annotate, decided=["us__MOCK__other"])
    for cases in ({"reopened": [case]}, {"decided": [case]}):
        with pytest.raises(SystemExit, match="outside modelStats"):
            board.run(mixed_answers(), edit_base=predict, **cases)


# Review r2, N1, through the real exporter: triage applies a decision to a
# case the new model did not re-open (here a MOCK decision on the ruled
# output, which the MOCK incumbents answer wrong; on the MOCK board the new
# model answers it right), so the release bundle's annotations carry the
# decided classes and sentence where the base board's do not.

MOCK_CASE_NOTE = {
    "country": "us",
    "case_annotation": "MOCK case note.",
    "case_failure_sources": "llm_error",
    "case_failure_subtypes": "thresholds_rates",
}


def carried_answers() -> dict:
    """mixed_answers() with the MOCK incumbents wrong on the ruled row; on
    the MOCK board the new model answers it right, so it joins none of the
    row's wrong models."""
    answers = mixed_answers()
    for model in MOCK_MODELS:
        answers[(model, RULED_ROW)] = "right" if model == NEW else "wrong"
    return answers


def mock_decision(key: tuple[str, str]) -> dict:
    """A MOCK adjudication of ``key`` with d2180's decided class."""
    return {
        "country": "us",
        "scenario_id": key[0],
        "variable": key[1],
        "adjudicated_on": "2026-11-01",
        "judge_model": "MOCK judge",
        "judge_failure_source": "llm_error",
        "adjudicated_failure_source": "prompt_ambiguity",
        "adjudicated_failure_subtype": "state_local_rule",
        "reasoning": "MOCK reasoning.",
    }


def decide_on_release(*keys, edit=None):
    """An ``annotate`` hook: a MOCK case note on ``keys`` in both boards, and
    on the release board each MOCK decision applied as triage applies it
    (apply_adjudications), then ``edit(rows, cases)``."""
    from policybench.adjudications import apply_adjudications

    def annotate(directory: Path, side: str) -> None:
        rows_path = directory / "us_audit_row_annotations.csv"
        cases_path = directory / "us_case_notes.csv"
        rows = pd.read_csv(rows_path).assign(country="us")
        cases = pd.DataFrame(
            [{"scenario_id": s, "variable": v, **MOCK_CASE_NOTE} for s, v in keys]
        )
        if side == "release":
            rows, cases, _ = apply_adjudications(
                rows, cases, [mock_decision(key) for key in keys]
            )
            if edit is not None:
                edit(rows, cases)
        rows.to_csv(rows_path, index=False)
        cases.to_csv(cases_path, index=False)

    return annotate


def test_check_a_passes_a_decision_on_a_carried_case_through_the_real_exporter(
    board,
):
    """With the MOCK decision on the ruled case applied to the release
    board's annotations, the real exporter moves the MOCK incumbents' cells
    there in their class fields and caseAnnotation. The build passes with the
    case decided and not re-opened, and with it re-opened; holding every case
    to the base, as before review r2's N1, refuses it."""
    answers = with_a_parsed_answer(carried_answers(), board.release_doc)
    annotate = decide_on_release(RULED)
    payload, base = board.run(answers, annotate=annotate, decided=[RULED_CASE])
    cells = _ruled_cells(payload["countries"]["us"])
    base_cells = _ruled_cells(base["countries"]["us"])
    for model in MOCK_INCUMBENTS:
        moved = {
            field
            for field in set(cells[model]) | set(base_cells[model])
            if cells[model].get(field) != base_cells[model].get(field)
        }
        # MOVED: the release's exclusion record unscores the ruled output.
        assert moved - set(MOVED) == {
            field for field, may in DECIDED_MAY_DIFFER.items() if may
        }
        assert cells[model]["failureSource"] == "prompt_ambiguity"
        assert "Developer adjudication (2026-11-01)" in cells[model]["caseAnnotation"]
    board.run(answers, annotate=annotate, reopened=[RULED_CASE])
    with pytest.raises(SystemExit, match="outside modelStats") as refused:
        board.run(answers, annotate=annotate)
    assert f"scenarioPredictions {RULED[0]} {RULED[1]}" in str(refused.value)


@pytest.mark.parametrize("what", ["undecided_case", "row_annotation"])
def test_check_a_refuses_what_a_carried_decision_does_not_explain(board, what):
    """The same MOCK decision on a case this release does not decide stops the
    build, though the ruled case is decided; and on the decided ruled case, a
    row annotation that differs from the base's stops it unless the case was
    re-opened (review r2, N1)."""
    answers = with_a_parsed_answer(carried_answers(), board.release_doc)
    for model in MOCK_INCUMBENTS:
        answers[(model, OTHER_ROW)] = "wrong"
    if what == "undecided_case":
        annotate, case = decide_on_release(RULED, OTHER), OTHER
    else:

        def reword(rows, cases):
            mask = (rows.scenario_id == RULED[0]) & (rows.variable == RULED[1])
            rows.loc[mask, "annotation"] = "MOCK: a wording no decision changed."

        annotate, case = decide_on_release(RULED, edit=reword), RULED
    with pytest.raises(SystemExit, match="outside modelStats") as refused:
        board.run(answers, annotate=annotate, decided=[RULED_CASE])
    assert f"scenarioPredictions {case[0]} {case[1]}" in str(refused.value)
    reopened = [f"us__{case[0]}__{case[1]}"]
    board.run(answers, annotate=annotate, decided=[RULED_CASE], reopened=reopened)


def _country(**sections) -> dict:
    return {"countries": {"us": sections}}


def test_base_restoration_ignores_the_new_models_rows_and_cells():
    live = _country(
        country="us",
        heatmap=[{"model": "a", "variable": "snap", "score": 1.0}],
        scenarioPredictions={"s": {"snap": {"a": {"prediction": 1.0}}}},
    )
    scoped = copy.deepcopy(live)
    us = scoped["countries"]["us"]
    us["heatmap"].append({"model": NEW, "variable": "snap", "score": 9.0})
    us["scenarioPredictions"]["s"]["snap"][NEW] = {"prediction": 9.0}
    assert driver.base_restoration_problems(scoped, live, {"a"}) == []
    us["heatmap"].append({"model": "a", "variable": "eitc", "score": 1.0})
    us["scenarioPredictions"]["t"] = {"snap": {"a": {"prediction": 1.0}}}
    assert driver.base_restoration_problems(scoped, live, {"a"}) == [
        "heatmap a eitc changed",
        "scenarioPredictions t snap a changed",
    ]


def test_base_restoration_names_at_most_its_limit():
    live = _country(heatmap=[{"model": "a", "variable": f"v{i}"} for i in range(12)])
    scoped = _country(heatmap=[])
    problems = driver.base_restoration_problems(scoped, live, {"a"})
    assert len(problems) == 8
    assert driver.base_restoration_problems(scoped, live, {"a"}, limit=20) == [
        f"heatmap a v{i} changed" for i in sorted(range(12), key=lambda i: f"v{i}")
    ]


@settings(max_examples=60, deadline=None)
@given(
    prediction=st.floats(allow_nan=False, allow_infinity=False),
    field=st.sampled_from(["prediction", "groundTruth", "scored", "explanation"]),
    annotation=st.sampled_from(sorted(DECIDED_MAY_DIFFER)),
    reopened=st.sampled_from(["none", "this", "another"]),
    decided=st.sampled_from(["none", "this", "another"]),
)
def test_base_restoration_holds_every_cell_field_but_reopened_annotations(
    prediction, field, annotation, reopened, decided
):
    """Property: an incumbent cell's annotation field may move on a re-opened
    case, and its class fields and caseAnnotation on a decided case (review
    r2, N1); a case id that names another case exempts nothing here; any
    other field, never; an unmoved board, always passes."""
    cell = {"prediction": prediction, "groundTruth": 1.0, "scored": True}
    live = _country(scenarioPredictions={"s": {"v": {"a": cell}}})
    ids = {"none": frozenset(), "this": frozenset({"us__s__v"})}
    ids["another"] = frozenset({"us__s__w", "us__t__v"})
    check = functools.partial(
        driver.base_restoration_problems,
        live=live,
        incumbents={"a"},
        reopened=ids[reopened],
        decided=ids[decided],
    )
    assert check(copy.deepcopy(live)) == []
    moved = copy.deepcopy(live)
    moved["countries"]["us"]["scenarioPredictions"]["s"]["v"]["a"][annotation] = "X"
    may = reopened == "this" or (decided == "this" and DECIDED_MAY_DIFFER[annotation])
    assert check(moved) == ([] if may else ["scenarioPredictions s v a changed"])
    moved = copy.deepcopy(live)
    entry = moved["countries"]["us"]["scenarioPredictions"]["s"]["v"]["a"]
    entry[field] = "a value no exporter wrote"
    assert check(moved) == ["scenarioPredictions s v a changed"]


@settings(
    max_examples=12,
    deadline=None,
    suppress_health_check=[
        HealthCheck.function_scoped_fixture,
        HealthCheck.too_slow,
        HealthCheck.data_too_large,
    ],
)
@given(kinds=st.lists(st.sampled_from(KINDS), min_size=CELLS, max_size=CELLS))
def test_for_any_answers_the_ruled_record_moves_only_its_own_output(board, kinds):
    # Any answers that leave each model a parsed answer in each output group.
    answers = with_a_parsed_answer(answer_map(kinds), board.release_doc)
    payload, base = board.run(answers)
    released = export_board(
        write_board(board.root / "released", answers, board.release_doc)
    )
    scoped = export_board(write_board(board.root / "scoped", answers, board.base_doc))
    assert payload == released
    now, before = released["countries"]["us"], scoped["countries"]["us"]
    # With the base's record put back, every incumbent is the base's, byte for
    # byte: adding Fable 5.2 moves no incumbent.
    previous = {row["model"]: row for row in base["countries"]["us"]["modelStats"]}
    assert set(previous) == set(MOCK_INCUMBENTS)
    assert driver.incumbent_drift(before["modelStats"], previous) == []
    # Excluding the ruled output changes no other output's cell, hit or score.
    for scenario, outputs in now["scenarioPredictions"].items():
        for variable, cell in outputs.items():
            old = before["scenarioPredictions"][scenario][variable]
            if (scenario, variable) != RULED:
                assert json.dumps(cell) == json.dumps(old)
                continue
            # It leaves every model's scored set, Fable 5.2's included.
            assert set(cell) == set(MOCK_MODELS)
            for model, entry in cell.items():
                assert (old[model]["scored"], entry["scored"]) == (True, False)
                assert {k: v for k, v in entry.items() if k not in MOVED} == {
                    k: v for k, v in old[model].items() if k not in MOVED
                }
    n_now = {row["model"]: row["n"] for row in now["modelStats"]}
    n_before = {row["model"]: row["n"] for row in before["modelStats"]}
    assert n_now == {model: n - 1 for model, n in n_before.items()}
    ruled = [r for r in board.release_doc["exclusions"] if driver.spec_key(r) == RULED]
    assert driver.exclusion_scope_problems(released, scoped, ruled) == []


@pytest.mark.parametrize("where", ["another output", "the ruled output"])
def test_an_incumbent_answer_changed_since_the_base_is_refused(board, where):
    base_answers = mixed_answers()
    answers = dict(base_answers)
    row = RULED_ROW if where == "the ruled output" else OTHER_ROW
    model = MOCK_INCUMBENTS[0]
    answers[(model, row)] = "missing" if answers[(model, row)] == "right" else "right"
    with pytest.raises(SystemExit, match="incumbent modelStats drift"):
        board.run(answers, base_answers=base_answers)


def _group():
    from policybench.spec import output_group_id

    return output_group_id(RULED[1])


def _other(rows, field="variable"):
    return next(row for row in rows if row.get(field) != _group())


def _ruled_group(rows):
    return next(row for row in rows if row.get("variable") == _group())


def _bump(row, field, by=1):
    row[field] = row[field] + by


def _ruled_cells(us) -> dict:
    return us["scenarioPredictions"][RULED[0]][RULED[1]]


def _ruled_entry(us) -> dict:
    (entry,) = [
        e
        for e in us["referenceExclusions"]
        if (e["scenarioId"], e["variable"]) == RULED
    ]
    return entry


def _stat(us, model=NEW) -> dict:
    (row,) = [row for row in us["modelStats"] if row["model"] == model]
    return row


def _segment(us, label) -> dict:
    (row,) = [row for row in us["failureModes"]["households"] if row["label"] == label]
    return row


def _reorder(row: dict) -> None:
    items = list(row.items())
    row.clear()
    row.update(reversed(items))


# The ruled household (scenario_122) lives in Minnesota, which taxes income,
# so this segment holds none of the ruled outputs.
UNRULED_SEGMENT = "No-income-tax states"


PAYLOAD_EDITS = {
    "another output's cell": lambda us: _bump(
        us["scenarioPredictions"][OTHER[0]][OTHER[1]][NEW], "exact", 100.0
    ),
    "the ruled cell's answer": lambda us: _bump(
        us["scenarioPredictions"][RULED[0]][RULED[1]][MOCK_INCUMBENTS[0]],
        "prediction",
        1.0,
    ),
    "a stable stat": lambda us: us["modelStats"][0].update(condition="tools"),
    "an n": lambda us: _bump(us["modelStats"][0], "n"),
    "an nParsed": lambda us: _bump(us["modelStats"][1], "nParsed", -1),
    "another output's heatmap entry": lambda us: _bump(_other(us["heatmap"]), "exact"),
    "the ruled output's heatmap n": lambda us: _bump(_ruled_group(us["heatmap"]), "n"),
    "another output's programStats": lambda us: _bump(
        _other(us["programStats"]), "exact"
    ),
    "another output's failure mode": lambda us: _bump(
        _other(us["failureModes"]["programs"]), "overallCorrectPct"
    ),
    "a household segment": lambda us: _bump(us["failureModes"]["households"][0], "n"),
    "an added exclusion entry": lambda us: us["referenceExclusions"].append(
        {**us["referenceExclusions"][0], "scenarioId": "scenario_000"}
    ),
    "a base exclusion entry": lambda us: us["referenceExclusions"][0].update(
        note="edited"
    ),
    "the scenarios": lambda us: us.update(scenarios={"edited": us["scenarios"]}),
    "the global weights": lambda us: us.update(
        globalWeights={"edited": us["globalWeights"]}
    ),
    # Review r1, M10 (S P3-3): the edits the review lists.
    "the ruled cell scored again": lambda us: _ruled_cells(us)[NEW].update(scored=True),
    "the ruled cell's excludedReason": lambda us: _ruled_cells(us)[NEW].update(
        excludedReason="MOCK reason"
    ),
    "the ruled cell's excludedInput": lambda us: _ruled_cells(us)[NEW].update(
        excludedInput="MOCK input"
    ),
    "a field added to the ruled cell": lambda us: _ruled_cells(us)[NEW].update(
        mock=1.0
    ),
    "one model's ruled cell removed": lambda us: _ruled_cells(us).pop(NEW),
    "the ruled group's programStats n": lambda us: _bump(
        _ruled_group(us["programStats"]), "n"
    ),
    "a segment without a ruled household": lambda us: _bump(
        _segment(us, UNRULED_SEGMENT), "correctPct"
    ),
    "a modelStats entry's field order": lambda us: _reorder(_stat(us)),
    "the ruled exclusion entry": lambda us: _ruled_entry(us).update(note="MOCK edited"),
}


@pytest.mark.parametrize("edit", sorted(PAYLOAD_EDITS))
def test_export_refuses_a_payload_moved_beyond_the_ruled_output(
    board, monkeypatch, edit
):
    import policybench.full_run_export

    real = policybench.full_run_export.export_full_run

    def moved(path, **kwargs):
        payload = real(path, **kwargs)
        staged = json.loads((Path(path) / "us" / EXCLUSIONS_NAME).read_text())
        if RULED in {driver.spec_key(r) for r in staged["exclusions"]}:
            PAYLOAD_EDITS[edit](payload["countries"]["us"])
        return payload

    monkeypatch.setattr(policybench.full_run_export, "export_full_run", moved)
    # A moved n fails the scored-count gate, which runs first.
    message = "must be scored on" if edit == "an n" else "beyond the ruled outputs"
    with pytest.raises(SystemExit, match=message):
        board.run(mixed_answers())


def test_a_staged_record_adding_another_output_is_refused_by_the_real_export(
    board, monkeypatch
):
    reference = board_references()
    value = float(
        reference.loc[
            (reference.scenario_id == OTHER[0]) & (reference.variable == OTHER[1]),
            "value",
        ].iloc[0]
    )
    another = _another_record()
    another.update(frozen_value=value, alternative_value=value + 1.0)
    doc = copy.deepcopy(board.release_doc)
    doc["exclusions"].insert(-1, another)
    monkeypatch.setattr(driver, "RELEASE_SCORED", ROWS - len(doc["exclusions"]))
    with pytest.raises(SystemExit, match="not the ruled outputs"):
        board.run(with_a_parsed_answer(mixed_answers(), doc), doc=doc)


@pytest.fixture(scope="module")
def exported_pair(tmp_path_factory):
    """The release and scope exports of one MOCK board, built once."""
    root = tmp_path_factory.mktemp("pair")
    base_doc, release_doc = board_docs()
    answers = mixed_answers()
    released = export_board(write_board(root / "released", answers, release_doc))
    scoped = export_board(write_board(root / "scoped", answers, base_doc))
    ruled = [r for r in release_doc["exclusions"] if driver.spec_key(r) == RULED]
    return released, scoped, ruled


def _perturbed(value):
    if isinstance(value, bool):
        return not value
    if isinstance(value, (int, float)):
        return value + 1
    if value is None:
        return 0.0
    return f"{value} (edited)"


# --- Review r1, M10 (S P3-3): every branch of exclusion_scope_problems --------
#
# Each edit moves the MOCK pair's release payload (now) or scope export
# (before) in one place, and names what the check must report. An edit
# marked exact reaches one branch alone, so the check reports that branch's
# line and nothing else; the others cause more lines, among them the branch's.

RULED_CELL = f"{RULED[0]} {RULED[1]}"
CELL_MOVED = "the record moves more than its scored flag and exclusion fields"
GROUP = RULED[1]  # state_refundable_credits is its own output group


def _scored_last(us) -> None:
    entry = _ruled_cells(us)[NEW]
    entry["scored"] = entry.pop("scored")


def _without_ruled_cells(now, before) -> None:
    for us in (now, before):
        del us["scenarioPredictions"][RULED[0]][RULED[1]]


def _without_new_ruled_cell(now, before) -> None:
    for us in (now, before):
        _ruled_cells(us).pop(NEW)


def _ruled_segment(now, before) -> dict:
    """The first household segment the ruled output's rows leave."""
    return next(
        row
        for row in now["failureModes"]["households"]
        if row["n"] != _segment(before, row["label"])["n"]
    )


SCOPE_EDITS = {
    "the ruled cell scored again": (
        lambda now, before: _ruled_cells(now)[NEW].update(scored=True),
        "exact",
        f"{RULED_CELL} {NEW}: {CELL_MOVED}",
    ),
    "the scope export's ruled cell already unscored": (
        lambda now, before: _ruled_cells(before)[NEW].update(scored=False),
        "exact",
        f"{RULED_CELL} {NEW}: {CELL_MOVED}",
    ),
    "the ruled cell's excludedReason": (
        lambda now, before: _ruled_cells(now)[NEW].update(excludedReason="MOCK"),
        "exact",
        f"{RULED_CELL} {NEW}: {CELL_MOVED}",
    ),
    "the ruled cell's excludedInput": (
        lambda now, before: _ruled_cells(now)[NEW].update(excludedInput="MOCK"),
        "exact",
        f"{RULED_CELL} {NEW}: {CELL_MOVED}",
    ),
    "a field added to the ruled cell": (
        lambda now, before: _ruled_cells(now)[NEW].update(mock=1.0),
        "exact",
        f"{RULED_CELL} {NEW}: {CELL_MOVED}",
    ),
    # Only the key-order clause sees it: the value clause skips scored.
    "the ruled cell's scored flag moved": (
        lambda now, before: _scored_last(now),
        "exact",
        f"{RULED_CELL} {NEW}: {CELL_MOVED}",
    ),
    "one model's ruled cell removed": (
        lambda now, before: _ruled_cells(now).pop(NEW),
        "among",
        f"{RULED_CELL}: its models changed",
    ),
    "one model's ruled cell removed from both": (
        _without_new_ruled_cell,
        "among",
        f"{NEW} lacks a cell of a ruled output",
    ),
    "the ruled output's cells removed from both": (
        _without_ruled_cells,
        "among",
        f"no cells in the payload for {[RULED]}",
    ),
    "a modelStats entry's field order": (
        lambda now, before: _reorder(_stat(now)),
        "exact",
        f"{NEW}'s modelStats fields changed",
    ),
    "a modelStats n": (
        lambda now, before: _bump(_stat(now), "n", -1),
        "exact",
        f"{NEW}'s n or nParsed does not fall by its ruled rows",
    ),
    "a modelStats nParsed": (
        lambda now, before: _bump(_stat(now), "nParsed"),
        "exact",
        f"{NEW}'s n or nParsed does not fall by its ruled rows",
    ),
    "the ruled group's heatmap nParsed": (
        lambda now, before: _bump(
            next(
                row
                for row in now["heatmap"]
                if (row["model"], row["variable"]) == (NEW, GROUP)
            ),
            "nParsed",
            -1,
        ),
        "exact",
        f"heatmap {(NEW, GROUP)}: n or nParsed does not fall by its rows",
    ),
    "the ruled group's heatmap field order": (
        lambda now, before: _reorder(
            next(
                row
                for row in now["heatmap"]
                if (row["model"], row["variable"]) == (NEW, GROUP)
            )
        ),
        "exact",
        f"heatmap {(NEW, GROUP)}: its fields changed",
    ),
    "the ruled group's programStats n": (
        lambda now, before: _bump(_ruled_group(now["programStats"]), "n"),
        "exact",
        f"programStats {(GROUP,)}: n or nParsed does not fall by its rows",
    ),
    "the ruled group's programStats nParsed": (
        lambda now, before: _bump(_ruled_group(now["programStats"]), "nParsed", -1),
        "exact",
        f"programStats {(GROUP,)}: n or nParsed does not fall by its rows",
    ),
    "a segment without a ruled household": (
        lambda now, before: _bump(_segment(now, UNRULED_SEGMENT), "correctPct"),
        "exact",
        f"failureModes segment {UNRULED_SEGMENT} moves beyond its rows",
    ),
    "the ruled exclusion entry": (
        lambda now, before: _ruled_entry(now).update(note="MOCK edited"),
        "exact",
        "referenceExclusions does not add exactly the records",
    ),
    "a base exclusion entry": (
        lambda now, before: now["referenceExclusions"][0].update(note="MOCK"),
        "exact",
        "referenceExclusions changes the base's entries",
    ),
}


def test_the_mock_pair_holds_what_the_scope_edits_assume(exported_pair):
    released, scoped, _ = exported_pair
    now, before = released["countries"]["us"], scoped["countries"]["us"]
    from policybench.spec import output_group_id

    assert output_group_id(RULED[1]) == GROUP
    # The segment the ruled household is not in keeps its rows; the ones it
    # is in lose the ruled output's three parsed rows.
    assert _segment(now, UNRULED_SEGMENT) == _segment(before, UNRULED_SEGMENT)
    assert before["failureModes"]["households"][0]["n"] > 0
    assert {
        _segment(before, row["label"])["n"] - row["n"]
        for row in now["failureModes"]["households"]
    } == {0, len(MOCK_MODELS)}
    assert all(entry["parsed"] is True for entry in _ruled_cells(now).values())


@pytest.mark.parametrize("edit", list(SCOPE_EDITS))
def test_each_branch_of_the_scope_check_refuses_its_edit(exported_pair, edit):
    released, scoped, ruled = exported_pair
    now, before = copy.deepcopy(released), copy.deepcopy(scoped)
    move, kind, line = SCOPE_EDITS[edit]
    move(now["countries"]["us"], before["countries"]["us"])
    problems = driver.exclusion_scope_problems(now, before, ruled)
    if kind == "exact":
        assert problems == [line]
    else:
        assert line in problems, problems


def test_a_ruled_segment_may_lose_only_its_rows(exported_pair):
    released, scoped, ruled = exported_pair
    now = copy.deepcopy(released)
    segment = _ruled_segment(now["countries"]["us"], scoped["countries"]["us"])
    _bump(segment, "n", -1)
    assert driver.exclusion_scope_problems(now, scoped, ruled) == [
        f"failureModes segment {segment['label']} moves beyond its rows"
    ]


# The fields of each model's ruled cell on the MOCK pair. mixed_answers has
# the new model answer the ruled output wrong and the incumbents right, so
# only the new model's cell carries failure annotations.
RULED_CELL_FIELDS = (
    "prediction",
    "groundTruth",
    "scored",
    "error",
    "parsed",
    "score",
    "boundedScore",
    "thresholdScore",
    "exact",
    "within1pct",
    "within5pct",
    "within10pct",
    "excludedReason",
    "excludedInput",
    "explanation",
)
RULED_CELLS = {
    NEW: (
        *RULED_CELL_FIELDS,
        "annotation",
        "failureSource",
        "failureSubtype",
        "referenceExplanation",
    ),
    **{
        model: (*RULED_CELL_FIELDS, "referenceExplanation") for model in MOCK_INCUMBENTS
    },
}


def test_the_perturbation_reaches_every_field_of_every_ruled_cell(exported_pair):
    released, _, _ = exported_pair
    cells = _ruled_cells(released["countries"]["us"])
    assert {model: tuple(entry) for model, entry in cells.items()} == RULED_CELLS


@pytest.mark.parametrize(
    "model, field",
    [(model, field) for model, fields in RULED_CELLS.items() for field in fields],
)
def test_a_change_to_any_field_of_a_ruled_cell_is_refused(exported_pair, model, field):
    released, scoped, ruled = exported_pair
    now = copy.deepcopy(released)
    entry = _ruled_cells(now["countries"]["us"])[model]
    entry[field] = _perturbed(entry[field])
    problems = driver.exclusion_scope_problems(now, scoped, ruled)
    assert f"{RULED_CELL} {model}: {CELL_MOVED}" in problems, problems


@settings(max_examples=60, deadline=None)
@given(data=st.data())
def test_any_single_cell_change_is_refused_wherever_it_is(exported_pair, data):
    released, scoped, ruled = exported_pair
    assert driver.exclusion_scope_problems(released, scoped, ruled) == []
    cells = released["countries"]["us"]["scenarioPredictions"]
    scenario = data.draw(st.sampled_from(sorted(cells)))
    variable = data.draw(st.sampled_from(sorted(cells[scenario])))
    model = data.draw(st.sampled_from(sorted(cells[scenario][variable])))
    field = data.draw(st.sampled_from(sorted(cells[scenario][variable][model])))
    mutated = copy.deepcopy(released)
    cell = mutated["countries"]["us"]["scenarioPredictions"][scenario][variable][model]
    cell[field] = _perturbed(cell[field])
    assert driver.exclusion_scope_problems(mutated, scoped, ruled)


# Review r1, M10 (S P3-4): every open row runs. Hypothesis draws of
# len(OPEN_ROWS) examples promise no particular row.
@pytest.mark.parametrize("row", OPEN_ROWS)
def test_excluding_any_one_output_never_changes_another_outputs_hit(tmp_path, row):
    reference = board_references()
    key = (reference.scenario_id[row], reference.variable[row])
    base_doc, release_doc = board_docs()
    (ruled,) = [r for r in release_doc["exclusions"] if driver.spec_key(r) == RULED]
    value = float(reference.value[row])
    record = copy.deepcopy(ruled)
    record.update(
        scenario_id=key[0],
        variable=key[1],
        frozen_value=value,
        alternative_value=1.0 - value if is_binary(key[1]) else value + 1.0,
    )
    doc = copy.deepcopy(base_doc)
    doc["exclusions"].insert(-1, record)
    answers = with_a_parsed_answer(mixed_answers(), doc)
    root = tmp_path / "any-one-output"
    scoped = export_board(write_board(root / "scoped", answers, base_doc))
    excluded = export_board(write_board(root / "excluded", answers, doc))
    now = excluded["countries"]["us"]["scenarioPredictions"]
    before = scoped["countries"]["us"]["scenarioPredictions"]
    for scenario, outputs in now.items():
        for variable, cell in outputs.items():
            if (scenario, variable) == key:
                assert all(entry["scored"] is False for entry in cell.values())
            else:
                assert json.dumps(cell) == json.dumps(before[scenario][variable])
    # The scope check holds the rest of the payload to the base's too, and
    # the exporter moves three things it holds with some exclusions: removing
    # a group's first scored row reorders the exporter's groups, and so the
    # prompts (scenarios) and globalWeights; removing a group's last parsed
    # answer on a nonzero reference drops programStats' mape; and an
    # eligibility output moves modelStats' accuracy. The check refuses those
    # and passes every other exclusion. The ruled output does none of the
    # three (tested below).
    from policybench.spec import output_group_id

    group = output_group_id(key[1])
    reordered = group_order(reference, doc) != group_order(reference, base_doc)
    refielded = [
        section
        for section in ("heatmap", "programStats")
        if [list(row) for row in group_entries(excluded, section, group)]
        != [list(row) for row in group_entries(scoped, section, group)]
    ]
    binary = is_binary(key[1])
    problems = driver.exclusion_scope_problems(excluded, scoped, [record])

    def explained(problem: str) -> bool:
        if problem in ("scenarios changed", "globalWeights changed"):
            return reordered
        if problem.endswith(": its fields changed"):
            return any(problem.startswith(f"{s} (") for s in refielded)
        if problem.endswith("'s accuracy changed"):
            return binary
        return False

    assert all(explained(problem) for problem in problems), problems
    if reordered:
        assert "scenarios changed" in problems
    for section in refielded:
        assert any(
            p.startswith(f"{section} (") and p.endswith(": its fields changed")
            for p in problems
        )
    if not (reordered or refielded or binary):
        assert problems == []


def group_entries(payload: dict, section: str, group: str) -> list[dict]:
    return [
        row for row in payload["countries"]["us"][section] if row["variable"] == group
    ]


def test_the_ruled_record_keeps_the_exporters_group_order_and_mape():
    from policybench.analysis import mean_absolute_percentage_error

    reference = pd.read_csv(io.BytesIO(base_blob(SNAPSHOT_PATH / CSV_NAME)))
    order = group_order(reference, release_record())
    assert order == group_order(reference, base_record())
    assert RULED[1] in order
    assert not is_binary(RULED[1])
    # Its reference is $0, and MAPE skips zero references, so no model's mape
    # for the group can move with it.
    (value,) = reference.loc[
        (reference.scenario_id == RULED[0]) & (reference.variable == RULED[1]),
        "value",
    ]
    assert value == 0.0
    with_it = mean_absolute_percentage_error(
        pd.Series([value, 10.0]).values, pd.Series([1921.0, 11.0]).values
    )
    assert with_it == mean_absolute_percentage_error(
        pd.Series([10.0]).values, pd.Series([11.0]).values
    )


# --- Preparation: prepare_inputs folds a MOCK complete run --------------------
#
# Review r1, M10 (S P3-4): the fold's property drives the driver's own
# prepare_inputs, with the setup of Terra's real-preparation tests
# (test_finish_terra.py's full_run): release 20261027's references from git
# as the committed snapshot, the treatment check recorded instead of run,
# and every answer MOCK.


def _mock_run_rows(reference: pd.DataFrame) -> pd.DataFrame:
    """A MOCK complete Claude Fable 5.2 run: every reference key, each
    answered with its reference value, with the runner's call provenance,
    usage and provider identity."""
    from policybench.config import MODELS as registry

    frame = reference[driver.KEY].copy()
    frame.insert(0, "model", NEW)
    frame["prediction"] = reference["value"].to_numpy()
    frame["explanation"] = 'MOCK answer, with "quotes".'
    frame["error"] = None
    frame["raw_response"] = '{"answer": 1}'
    frame["live_calls"] = 1
    frame["cache_hit_calls"] = 0
    frame["live_elapsed_seconds"] = 1.5
    frame["elapsed_seconds"] = 1.5
    frame["estimated_cost_usd"] = 0.001
    frame["total_tokens"] = 900
    frame["provider_resolved_model"] = driver.resolved_model_id(registry[NEW])
    frame["provider_response_id"] = [f"resp_mock_{i}" for i in range(len(frame))]
    return frame


# A run's key set, changed, and what prepare_inputs answers.
KEY_CHANGES = {
    "none": None,
    "an output dropped": "prediction keys differ from reference",
    "an output repeated": "duplicate prediction keys",
    "an output renamed": "prediction keys differ from reference",
}


# The first two examples always run: a fold with missing answers and an
# optional column, and the plainest one.
@example(count=2, value=7, missing={0, 1983}, change="none", at=0, extra=True)
@example(count=1, value=0, missing=set(), change="none", at=0, extra=False)
@settings(max_examples=10, deadline=None)
@given(
    count=st.integers(1, 3),
    value=st.integers(-10000, 10000),
    missing=st.sets(st.integers(0, driver.BASE_OUTPUTS - 1), max_size=8),
    change=st.sampled_from(list(KEY_CHANGES)),
    at=st.integers(0, driver.BASE_OUTPUTS - 1),
    extra=st.booleans(),
)
def test_the_fold_adds_exactly_1984_fable52_rows_on_the_reference_key_set(
    tmp_path_factory, count, value, missing, change, at, extra
):
    """prepare_inputs, for any incumbent count, any missing answers and any
    change to the run's key set: it refuses a run whose keys are not the
    reference's, before it publishes anything; otherwise the fold keeps
    every incumbent row and adds exactly 1,984 Claude Fable 5.2 rows, on the
    reference key set, its missing answers missing and its cells the run's
    text. The base's record excludes 49 outputs from scoring, never from the
    fold."""
    # One folder, cleared for each example and removed after it: an example
    # writes about 10 MB, and the basetemp must stay under 1 GB however many
    # examples Hypothesis runs or shrinks through.
    root = tmp_path_factory.getbasetemp() / "fable52-prepare"
    shutil.rmtree(root, ignore_errors=True)
    try:
        _prepare_and_check(root, count, value, missing, change, at, extra)
    finally:
        shutil.rmtree(root, ignore_errors=True)


# One MOCK run row that prepare_inputs refuses, as Terra's
# test_real_preparation_checks_provider_identity_and_disclosures refuses a
# whole run: verify_usage's and verify_call_provenance's own messages.
ROW_DEFECTS = {
    "a negative cost": ({"estimated_cost_usd": -0.5}, "invalid estimated_cost_usd"),
    "an infinite token count": (
        {"total_tokens": float("inf")},
        "invalid total_tokens",
    ),
    "a negative live call count": ({"live_calls": -1}, "invalid call provenance"),
    "live time over the elapsed time": (
        {"live_elapsed_seconds": 9.0},
        "inconsistent call provenance",
    ),
}


@pytest.mark.parametrize("defect", ROW_DEFECTS.values(), ids=ROW_DEFECTS)
def test_preparation_refuses_a_row_with_invalid_usage_or_call_provenance(
    tmp_path, defect
):
    """Review r1, M11 (S P3-5): one bad row of the MOCK run stops
    prepare_inputs before the treatment check and before it publishes
    anything. Before M11 no test of the three new files reached verify_usage's
    validity check."""
    _prepare_and_check(tmp_path / "prepare", 1, 0, set(), "none", 17, False, defect)


def _prepare_and_check(
    root, count, value, missing, change, at, extra, defect=None
) -> None:
    import freeze_gpt61sol
    import freeze_snapshot as freezer

    from policybench.config import MODELS as registry

    snapshot = base_references(root / "snapshot")
    reference = pd.read_csv(snapshot / CSV_NAME)
    assert len(reference) == driver.BASE_OUTPUTS
    annotations = root / "annotations"
    annotations.mkdir()
    for name in driver.ANNOTATION_FILES:
        (annotations / name).write_text(f"MOCK {name}\n")
    incumbents = [f"mock-incumbent-{index}" for index in range(count)]
    base = pd.concat(
        [
            reference[driver.KEY].assign(
                model=model,
                prediction=float(value),
                explanation='MOCK answer, with "quotes".',
                raw_response="{}",
                provider_resolved_model=model,
                prompt_tokens=100.0,
                completion_tokens=25.0,
                error=None,
            )
            for model in incumbents
        ],
        ignore_index=True,
    )[["model", *driver.KEY, *freezer.PREDICTION_EVIDENCE_COLUMNS[2:]]]
    frame = _mock_run_rows(reference)
    gaps = sorted(missing)
    frame.loc[gaps, "prediction"] = None
    frame.loc[gaps, "error"] = "MOCK: no answer parsed"
    if extra:
        frame["provider_system_fingerprint"] = "fp_mock"
    if change == "an output dropped":
        frame = frame.drop(index=at)
    elif change == "an output repeated":
        frame = pd.concat([frame, frame.iloc[[at]]], ignore_index=True)
    elif change == "an output renamed":
        frame.loc[at, "variable"] = "mock_unknown_output"
    if defect is not None:
        for column, bad in defect[0].items():
            frame[column] = frame[column].astype(type(bad))
            frame.loc[frame.index[at], column] = bad
    run_dir = root / "runs" / SLUG / "run"
    run_dir.mkdir(parents=True)
    frame.to_csv(run_dir / "predictions.csv", index=False)
    state = {
        "model": NEW,
        "completed": 100,
        "total": 100,
        "stopped_reason": None,
        "treatment_fingerprint": {"model_id": registry[NEW]},
    }
    driver.write_json(run_dir / "run_state.json", state)
    stage, checked = root / "stage", []
    args = SimpleNamespace(stage_dir=stage, partial=False)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(driver, "SNAPSHOT", snapshot)
        patch.setattr(driver, "ANNOTATIONS", annotations)
        patch.setattr(driver, "BOARD_MODELS", count + 1)
        patch.setattr(
            freeze_gpt61sol,
            "validate_treatment",
            lambda freezer, state, path, scenarios: checked.append(path),
        )
        runs = driver.discover_new_models(root / "runs")
        refusal = KEY_CHANGES[change] or (defect[1] if defect else None)
        if refusal:
            with pytest.raises(SystemExit, match=refusal):
                driver.prepare_inputs(args, runs, base, reference)
            assert not (stage / "publish").exists()
            assert checked == []
            return
        bundle, frames = driver.prepare_inputs(args, runs, base, reference)
    assert checked == [run_dir / "run_state.json"]
    assert list(frames) == [NEW] and len(frames[NEW]) == driver.BASE_OUTPUTS
    folded = pd.read_csv(bundle / "us/predictions.csv", low_memory=False)
    assert sorted(set(folded.model)) == sorted([*incumbents, NEW])
    new_rows = folded[folded.model == NEW]
    assert len(new_rows) == 1984 == driver.BASE_OUTPUTS
    keys = set(new_rows[driver.KEY].itertuples(index=False, name=None))
    assert keys == set(reference[driver.KEY].itertuples(index=False, name=None))
    assert RULED in keys
    assert {driver.spec_key(r) for r in BASE_RECORD["exclusions"]} <= keys
    unanswered = new_rows[new_rows.prediction.isna()]
    assert set(unanswered[driver.KEY].itertuples(index=False, name=None)) == {
        (reference.scenario_id[row], reference.variable[row]) for row in gaps
    }
    assert set(frame.columns) <= set(new_rows.columns)
    # restore_run_row_text: the new model's cells are the run's own text.
    text = functools.partial(pd.read_csv, dtype=str, keep_default_na=False)
    source = text(run_dir / "predictions.csv").set_index(driver.KEY)
    restored = text(bundle / "us/predictions.csv")
    restored = restored[restored.model == NEW].set_index(driver.KEY)
    assert restored[list(source.columns)].sort_index().equals(source.sort_index())
    staged_base = pd.read_csv(io.StringIO(base.to_csv(index=False)))
    for model in incumbents:
        assert freezer._model_prediction_rows_sha256(
            folded, model
        ) == freezer._model_prediction_rows_sha256(staged_base, model)
    provenance = json.loads((stage / "model-provenance.json").read_text())
    assert provenance[NEW]["rows"] == 1984 and provenance[NEW]["households"] == 100
    assert provenance[NEW]["provider_system_fingerprints"] == (
        ["fp_mock"] if extra else []
    )


# --- Verdicts: a bound sidecar and the template version its case requires -----
#
# The helpers port test_finish_terra.py's: MOCK verdicts, sidecars and the
# isolated judge's transcript shape.

JUDGED = "Classify these wrong answers.\n"


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


def _event(kind, **fields):
    return {"type": kind, **fields}


def _attachment(kind, **fields):
    return _event("attachment", attachment={"type": kind, **fields})


def _call(name, call_id, answer=None, effort="xhigh"):
    content = [{"type": "tool_use", "id": call_id, "name": name, "input": answer or {}}]
    return _event("assistant", effort=effort, message={"content": content})


def _result(call_id):
    part = {"type": "tool_result", "tool_use_id": call_id, "content": "done"}
    return _event("user", message={"content": [part]})


def _clean_transcript(effort="xhigh", prompt=JUDGED, models=(NEW,)):
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
                "judged_at_utc": "2026-11-10T12:00:00+00:00",
                "judge_template_version": driver.JUDGE_TEMPLATE_VERSION,
                "judge_isolation": {"tools": "none (--tools '')"},
                "judge_auth": {"method": "oauth_token", "account": None, "org": None},
                "judge_account_declared": (
                    "claude setup-token login (token sha256 6a6daf56361b), "
                    "Max 2026-09-30"
                ),
                "judge_effort": "xhigh",
                **meta,
            }.items()
            if v is not None
        },
    )
    if (case / "prompt.md").is_file():
        events = _clean_transcript(
            prompt=(case / "prompt.md").read_text(),
            effort=meta.get("judge_effort", "xhigh"),
        )
        events[7]["message"]["content"][0]["input"] = verdict
        _write_transcript(case, events)


def _audit(root: Path, wrong_models, version=2) -> Path:
    from policybench.judge_template import template_header

    case = root / "cases/us__s1__snap"
    case.mkdir(parents=True)
    (case / "prompt.md").write_text(template_header(version) + "\nMOCK question.\n")
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
def audit(tmp_path):
    root = tmp_path / "audit"
    case = _audit(root, [NEW])
    verdict = _verdict([NEW])
    write_verdict(case, verdict)
    return root, case, verdict


def _seed(case: Path) -> dict:
    return {
        case.name: {
            "prompt_sha256": sha(case / "prompt.md"),
            "verdict_sha256": sha(case / "verdict.json"),
        }
    }


def test_a_bound_v2_opus_verdict_passes(audit):
    assert driver.validate_verdicts(audit[0]) == []


def test_a_new_verdict_without_its_sidecar_is_pending_and_set_aside(audit):
    root, case, _ = audit
    (case / "verdict.meta.json").unlink()
    assert driver.validate_verdicts(root) == [case.name]
    assert driver.validate_verdicts(root, remove_invalid=True) == [case.name]
    assert not (case / "verdict.json").exists()


def test_a_carried_verdict_without_its_sidecar_is_refused(audit):
    root, case, _ = audit
    seed = _seed(case)
    (case / "verdict.meta.json").unlink()
    with pytest.raises(SystemExit, match="carried-over verdicts differ"):
        driver.validate_verdicts(root, seed=seed)


@pytest.mark.parametrize("version", [1, 3, None])
def test_a_new_verdict_on_another_template_version_is_pending(audit, version):
    root, case, verdict = audit
    write_verdict(case, verdict, judge_template_version=version)
    assert driver.validate_verdicts(root) == [case.name]


def test_a_reopened_case_cannot_pass_on_a_v1_prompt(audit):
    from policybench.judge_template import template_header

    root, case, verdict = audit
    (case / "prompt.md").write_text(template_header(1) + "\nMOCK question.\n")
    write_verdict(case, verdict)
    assert driver.validate_verdicts(root) == [case.name]


def test_a_carried_verdict_keeps_the_version_its_sidecar_records(tmp_path):
    """MOCK: a seed case judged on template v1 by another judge, as release
    20261027's oldest carried verdicts were. Carried, it passes; offered as a
    new verdict, it is pending."""
    root = tmp_path / "audit"
    case = _audit(root, ["incumbent-a"], version=1)
    write_verdict(
        case,
        _verdict(["incumbent-a"]),
        judge_model_requested="default",
        judge_model_reported=["gpt-6.1-sol"],
        judge_runner="scripts/run_audit_codex.sh",
        judge_template_version=1,
    )
    assert driver.validate_verdicts(root, seed=_seed(case)) == []
    assert driver.validate_verdicts(root) == [case.name]


def test_carried_verdicts_keep_the_seeds_bytes(audit):
    root, case, verdict = audit
    seed = _seed(case)
    assert driver.validate_verdicts(root, seed=seed) == []
    verdict["rationale"] += " Changed."
    write_verdict(case, verdict)
    with pytest.raises(SystemExit, match="carried-over verdicts differ"):
        driver.validate_verdicts(root, seed=seed)


# --- The judge's identity and isolation ---------------------------------------
# validate_verdicts alone holds a new verdict to this release's judge: Claude
# Opus 5.5, requested and reported, through scripts/run_audit_claude.sh, its
# verdict stamped in UTC. Each case breaks one field of an otherwise valid
# MOCK verdict (None drops the field).

NEW_MODEL_API_ID = "claude-fable-5-2"
IDENTITY_DEFECTS = {
    "requested the new model": {"judge_model_requested": NEW_MODEL_API_ID},
    "requested the new model's board id": {"judge_model_requested": NEW},
    "requested no model": {"judge_model_requested": None},
    "reported the new model": {"judge_model_reported": [NEW_MODEL_API_ID]},
    "reported the judge and the new model": {
        "judge_model_reported": [driver.JUDGE_MODEL, NEW_MODEL_API_ID]
    },
    "reported no model": {"judge_model_reported": []},
    "reported the judge as a string": {"judge_model_reported": driver.JUDGE_MODEL},
    "reported nothing": {"judge_model_reported": None},
    "another runner": {"judge_runner": "scripts/run_audit_codex.sh"},
    "no runner": {"judge_runner": None},
    "a stamp without an offset": {"judged_at_utc": "2026-11-10T12:00:00"},
    "a stamp in US Eastern time": {"judged_at_utc": "2026-11-10T07:00:00-05:00"},
    "a stamp an hour east of UTC": {"judged_at_utc": "2026-11-10T13:00:00+01:00"},
    "a day without a time": {"judged_at_utc": "2026-11-10"},
    "an unreadable stamp": {"judged_at_utc": "10 November 2026"},
    "no stamp": {"judged_at_utc": None},
}


def _set_aside_reason(root: Path, case: Path) -> str:
    (reason,) = (root.parent / "rejected-verdicts" / case.name).glob("*/reason.txt")
    return reason.read_text()


@pytest.mark.parametrize("stamp", ["2026-11-10T12:00:00Z", "2026-11-10T12:00:00+00:00"])
def test_a_new_verdict_stamped_in_utc_passes(audit, stamp):
    root, case, verdict = audit
    write_verdict(case, verdict, judged_at_utc=stamp)
    assert driver.validate_verdicts(root) == []


@pytest.mark.parametrize("override", IDENTITY_DEFECTS.values(), ids=IDENTITY_DEFECTS)
def test_a_new_verdict_from_another_judge_is_pending_and_set_aside(audit, override):
    root, case, verdict = audit
    write_verdict(case, verdict, **override)
    assert driver.validate_verdicts(root) == [case.name]
    assert driver.validate_verdicts(root, remove_invalid=True) == [case.name]
    assert not (case / "verdict.json").exists()
    assert "Opus 5.5 provenance" in _set_aside_reason(root, case)


@pytest.mark.parametrize("override", IDENTITY_DEFECTS.values(), ids=IDENTITY_DEFECTS)
def test_a_reopened_case_of_incumbents_alone_still_needs_this_releases_judge(
    tmp_path, override
):
    """A case judged anew whose wrong models are MOCK incumbents alone (its
    prompt changed, so it is not carried) is held to this release's judge."""
    root = tmp_path / "audit"
    case = _audit(root, ["incumbent-a"])
    write_verdict(case, _verdict(["incumbent-a"]))
    assert driver.validate_verdicts(root) == []
    write_verdict(case, _verdict(["incumbent-a"]), **override)
    assert driver.validate_verdicts(root, remove_invalid=True) == [case.name]
    assert "Opus 5.5 provenance" in _set_aside_reason(root, case)


@pytest.mark.parametrize("override", IDENTITY_DEFECTS.values(), ids=IDENTITY_DEFECTS)
def test_a_carried_verdict_naming_the_new_model_needs_this_releases_judge(
    audit, override
):
    """A verdict carried from the seed that names the new model (MOCK: the
    seed predates it) is held to this release's judge too, and a carried
    verdict that fails stops the step: a re-judge cannot restore it."""
    root, case, verdict = audit
    write_verdict(case, verdict, **override)
    with pytest.raises(SystemExit, match="Opus 5.5 provenance"):
        driver.validate_verdicts(root, seed=_seed(case))


def _edit_transcript(case: Path, edit) -> None:
    path = case / "claude.transcript.jsonl"
    events = [json.loads(line) for line in path.read_text().splitlines()]
    edit(events)
    _write_transcript(case, events)


def _answer_rationale(events) -> None:
    events[7]["message"]["content"][0]["input"]["rationale"] += " MOCK edit."


ISOLATION_DEFECTS = {
    "no judge_isolation": lambda case, v: write_verdict(case, v, judge_isolation=None),
    "an API key login": lambda case, v: write_verdict(
        case, v, judge_auth={"method": "api_key", "account": None, "org": None}
    ),
    "no login record": lambda case, v: write_verdict(case, v, judge_auth=None),
    "a login record that is not an object": lambda case, v: write_verdict(
        case, v, judge_auth="oauth_token"
    ),
    "no transcript": lambda case, v: (case / "claude.transcript.jsonl").unlink(),
    "a second user text message": lambda case, v: _edit_transcript(
        case,
        lambda events: events.insert(
            1, _event("user", message={"content": "MOCK second message."})
        ),
    ),
    "a user message other than prompt.md": lambda case, v: _edit_transcript(
        case, lambda events: events[0]["message"].update(content="MOCK other.")
    ),
    "an answer other than verdict.json": lambda case, v: _edit_transcript(
        case, _answer_rationale
    ),
    "a second accepted answer": lambda case, v: _edit_transcript(
        case,
        lambda events: events.extend(
            [_call("StructuredOutput", "call-2", v), _result("call-2")]
        ),
    ),
    "another tool call": lambda case, v: _edit_transcript(
        case, lambda events: events.insert(7, _call("Bash", "call-0"))
    ),
    "a working directory inside a git repository": lambda case, v: _edit_transcript(
        case, lambda events: events[1]["attachment"]["snapshot"].update(isGitRepo=True)
    ),
    "a turn at another effort": lambda case, v: _edit_transcript(
        case, lambda events: events[6].update(effort="low")
    ),
    # Review r2, N2: one defect for each set or pattern the check reads
    # (JUDGE_ATTACHMENTS, JUDGE_EVENT_TYPES, EMAIL_ADDRESS, ACCOUNT_KEY).
    "an unlisted attachment": lambda case, v: _edit_transcript(
        case, lambda events: events.insert(2, _attachment("skill_listing"))
    ),
    "an unlisted event type": lambda case, v: _edit_transcript(
        case, lambda events: events.insert(2, _event("system", subtype="init"))
    ),
    "an e-mail address in a context attachment": lambda case, v: _edit_transcript(
        case,
        lambda events: events[4]["attachment"].update(note="mock.judge@example.com"),
    ),
    "an account key in a context attachment": lambda case, v: _edit_transcript(
        case, lambda events: events[4]["attachment"].update(accountUuid="MOCK")
    ),
}


@pytest.mark.parametrize("defect", ISOLATION_DEFECTS.values(), ids=ISOLATION_DEFECTS)
def test_a_new_verdict_without_the_judges_isolation_is_pending(audit, defect):
    root, case, verdict = audit
    defect(case, verdict)
    assert driver.validate_verdicts(root) == [case.name]
    assert driver.validate_verdicts(root, remove_invalid=True) == [case.name]
    assert "judge isolation" in _set_aside_reason(root, case)


@pytest.mark.parametrize("defect", ISOLATION_DEFECTS.values(), ids=ISOLATION_DEFECTS)
def test_the_provenance_gate_refuses_a_verdict_without_the_judges_isolation(
    audit, tmp_path, defect
):
    """verify_judge_provenance, which export runs, checks each re-opened
    case's isolation again on the staged files."""
    root, case, verdict = audit
    rejudged = frozenset({case.name})
    record = tmp_path / "judge_provenance.json"
    driver.write_json(record, driver.judge_provenance_record(root / "cases", rejudged))
    driver.verify_judge_provenance(root / "cases", rejudged, record)
    defect(case, verdict)
    with pytest.raises(SystemExit, match="new verdicts disagree"):
        driver.verify_judge_provenance(root / "cases", rejudged, record)


# --- The ruled wave in the adjudication record ---------------------------------

BASE_WAVES = (
    "(2026-09-05, 2026-09-22, 2026-09-29, 2026-10-05, 2026-10-06, "
    "2026-10-10 or 2026-10-14)."
)
RELEASE_WAVES = (
    "(2026-09-05, 2026-09-22, 2026-09-29, 2026-10-05, 2026-10-06, "
    "2026-10-10, 2026-10-14 or 2026-11-01)."
)
WAVE_SENTENCE = (
    " The 2026-11-01 wave's decision follows Max's ruling of 2026-11-01 "
    f"(21:06 UTC) and was written on {WRITTEN_ON} UTC."
)


def test_the_record_names_the_ruled_wave_once_the_lead_fills_its_day(filled):
    conventions = driver.base_adjudication_record()["date_conventions"]
    assert conventions.count(BASE_WAVES) == 1
    expected = conventions.replace(BASE_WAVES, RELEASE_WAVES).replace(
        driver.DATE_CONVENTIONS_ANCHOR, driver.DATE_CONVENTIONS_ANCHOR + WAVE_SENTENCE
    )
    assert driver.release_date_conventions(conventions) == expected


@pytest.mark.parametrize("written", ["2026-11-01", WRITTEN_ON, "2026-12-31"])
def test_the_shared_record_test_reads_the_day_the_driver_writes(monkeypatch, written):
    """A differential check: tests/test_adjudications.py reads each later
    wave's written day from the committed record's date conventions, one
    sentence per wave, after the first three waves' sentence. The driver
    writes the ruled wave's one record as "decision ... was written", a form
    no earlier release wrote; the shared reader reads the spec's day from it,
    and every earlier wave's day as before."""
    from tests.test_adjudications import _wave_written_day

    spec = filled_spec(adjudications_written_on=written)
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    conventions = driver.release_date_conventions(
        driver.base_adjudication_record()["date_conventions"]
    )
    rest = conventions.split("before its decisions were written. ", 1)[1]
    days = {}
    for wave in ("2026-10-05", "2026-10-06", "2026-10-10", "2026-10-14", "2026-11-01"):
        sentence, rest = rest.split(". ", 1)
        days[wave] = _wave_written_day(sentence, wave)
    assert days == {
        "2026-10-05": "2026-10-06",
        "2026-10-06": "2026-10-09",
        "2026-10-10": "2026-10-10",
        "2026-10-14": "2026-10-14",
        "2026-11-01": written,
    }


@pytest.mark.parametrize(
    "value",
    [
        "[LEAD: the UTC day --step adjudicate-exclusions runs, YYYY-MM-DD]",
        "",
        None,
        "2026-11-1",
        "2026-13-01",
        "10 November 2026",
    ],
)
def test_a_missing_or_placeholder_written_day_stops_the_record(monkeypatch, value):
    spec = filled_spec(adjudications_written_on=value)
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    conventions = driver.base_adjudication_record()["date_conventions"]
    with pytest.raises(SystemExit, match="names no adjudications_written_on"):
        driver.release_date_conventions(conventions)


def test_the_record_gate_stops_while_the_spec_holds_its_placeholder(monkeypatch):
    spec = filled_spec(adjudications_written_on=WRITTEN_PLACEHOLDER)
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    base = driver.base_adjudication_record()
    with pytest.raises(SystemExit, match="names no adjudications_written_on"):
        driver.verify_record_form(driver.record_text(base), base)


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"adjudications_written_on": "2026-10-31"}, "precedes the ruling"),
        ({"wave_sentence": ""}, "names no wave_sentence"),
        ({"wave_sentence": "[LEAD: words]"}, "names no wave_sentence"),
    ],
)
def test_the_ruled_waves_day_and_words_are_checked(monkeypatch, changes, message):
    spec = filled_spec(**changes)
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    conventions = driver.base_adjudication_record()["date_conventions"]
    with pytest.raises(SystemExit, match=message):
        driver.release_date_conventions(conventions)


@settings(max_examples=60, deadline=None)
@given(day=st.dates())
def test_utc_day_keeps_every_calendar_day_and_refuses_placeholders(day):
    text = day.isoformat()
    assert driver.utc_day(text) == text
    assert driver.utc_day(f"[LEAD: {text}]") is None
    assert driver.utc_day(f"{text} ") is None
    assert driver.utc_day(text.replace("-", "/")) is None


def test_utc_today_is_the_utc_date():
    before = dt.datetime.now(dt.UTC).date().isoformat()
    today = driver.utc_today()
    after = dt.datetime.now(dt.UTC).date().isoformat()
    assert before <= today <= after
    assert driver.utc_day(today) == today


# --- The triage wave's written day (review r1, M16: E F3) ---------------------
#
# The spec starts with no triage decision. These tests give it a MOCK one,
# dated by a MOCK triage wave, to reach the triage wave's sentence.

TRIAGE_DAY = "2026-11-12"
MOCK_TRIAGE_ITEM = {
    "scenario_id": "scenario_901",
    "variable": "mock_output",
    "adjudicated_failure_source": "llm_error",
    "adjudicated_failure_subtype": "thresholds_rates",
    "adjudicated_on": TRIAGE_DAY,
    "reference_verdict": None,
    "reference_basis": None,
    "reasoning": "MOCK: the rows the judge classed outside the final set.",
}


def triage_spec(written=TRIAGE_DAY, **changes) -> dict:
    """The filled spec with the MOCK triage decision and its two days."""
    return filled_spec(
        triage_adjudications=[dict(MOCK_TRIAGE_ITEM)],
        triage_decided_on=TRIAGE_DAY,
        triage_adjudications_written_on=written,
        **changes,
    )


@pytest.mark.parametrize(
    "value",
    [
        "[LEAD: the UTC day the triage decisions were written, YYYY-MM-DD]",
        "",
        None,
        "2026-11-1",
        "2026-13-01",
        "12 November 2026",
        " 2026-11-12",
    ],
)
def test_a_missing_or_placeholder_triage_written_day_stops_the_record(
    monkeypatch, value
):
    """Before M16 any non-blank string passed here, the placeholder too."""
    spec = triage_spec(written=value)
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    wave = driver.decision_wave(driver.triage_items(spec))
    conventions = driver.base_adjudication_record()["date_conventions"]
    with pytest.raises(SystemExit, match="names no triage_adjudications_written_on"):
        driver.release_date_conventions(conventions, wave)


@settings(max_examples=60, deadline=None)
@given(
    wave_day=st.dates(min_value=dt.date(2026, 11, 2), max_value=dt.date(2027, 12, 31)),
    written=st.dates(min_value=dt.date(2026, 10, 1), max_value=dt.date(2028, 1, 31)),
)
@example(wave_day=dt.date(2026, 11, 12), written=dt.date(2026, 11, 2))
@example(wave_day=dt.date(2026, 11, 12), written=dt.date(2026, 11, 12))
def test_the_triage_waves_written_day_falls_on_or_after_its_wave(wave_day, written):
    """The review's case (decided 2026-11-12, written 2026-11-02) stops the
    record; a day on or after the wave's names the wave and the day once."""
    item = dict(MOCK_TRIAGE_ITEM, adjudicated_on=wave_day.isoformat())
    spec = filled_spec(
        triage_adjudications=[item],
        triage_decided_on=wave_day.isoformat(),
        triage_adjudications_written_on=written.isoformat(),
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
        wave = driver.decision_wave(driver.triage_items(spec))
        conventions = driver.base_adjudication_record()["date_conventions"]
        if written < wave_day:
            with pytest.raises(SystemExit, match="precedes the triage decisions"):
                driver.release_date_conventions(conventions, wave)
            return
        out = driver.release_date_conventions(conventions, wave)
    assert out.count(f"2026-11-01 or {wave_day.isoformat()}).") == 1
    sentence = (
        f" The {wave_day.isoformat()} wave's decisions keep scored outputs on "
        "cases this release's new models re-opened, resolving rows the judge "
        f"gave a class outside the final set, and were written on "
        f"{written.isoformat()} UTC."
    )
    assert out.count(sentence) == 1


# --- Each wave's written day against its verdicts and today (M16: E F4) -------


def _dated(key, judged, rejudged=None) -> dict:
    """A MOCK entry for ``key`` whose recorded verdict is dated ``judged``
    (judged_on_utc), or ``rejudged`` (judge_rejudged_on) when given."""
    entry = {"country": "us", "scenario_id": key[0], "variable": key[1]}
    if judged is not None:
        entry["judged_on_utc"] = judged
    if rejudged is not None:
        entry["judge_rejudged_on"] = rejudged
    return entry


DAYS = st.dates(min_value=dt.date(2026, 10, 1), max_value=dt.date(2026, 12, 31))


@settings(max_examples=120, deadline=None)
@given(
    judged=DAYS,
    rejudged=st.none() | DAYS,
    written=st.dates(min_value=dt.date(2026, 11, 1), max_value=dt.date(2026, 12, 31)),
    today=st.none() | DAYS,
    other=DAYS,
)
@example(
    judged=dt.date(2026, 11, 10),
    rejudged=None,
    written=dt.date(2026, 11, 1),
    today=None,
    other=dt.date(2026, 10, 1),
)
def test_the_ruled_wave_is_written_after_its_verdict_and_by_today(
    judged, rejudged, written, today, other
):
    """Accepted exactly when the ruled entry's recorded verdict (its
    judge_rejudged_on when present, else judged_on_utc) falls on or before
    the written day and, with ``today``, the written day on or before today.
    An entry outside the wave never counts. The explicit example is the
    review's: the ruling's own day entered for a verdict judged later."""
    spec = filled_spec(adjudications_written_on=written.isoformat())
    entries = [
        _dated(("scenario_902", "mock_other"), other.isoformat()),
        _dated(
            RULED,
            judged.isoformat(),
            None if rejudged is None else rejudged.isoformat(),
        ),
    ]
    day = judged if rejudged is None else rejudged
    on = None if today is None else today.isoformat()
    if today is not None and written > today:
        with pytest.raises(SystemExit, match="falls after today's UTC date"):
            driver.verify_written_days(entries, spec, today=on)
    elif day > written:
        with pytest.raises(SystemExit, match="precedes the day of a verdict"):
            driver.verify_written_days(entries, spec, today=on)
    else:
        driver.verify_written_days(entries, spec, today=on)


@pytest.mark.parametrize(
    "triage_judged, written, today, message",
    [
        ("2026-11-12", "2026-11-12", "2026-11-12", None),
        ("2026-11-11", "2026-11-13", None, None),
        ("2026-11-13", "2026-11-12", None, "triage_adjudications_written_on"),
        ("2026-11-12", "2026-11-14", "2026-11-13", "falls after today"),
        (None, "2026-11-12", None, "names no day"),
    ],
)
def test_the_triage_wave_is_written_after_its_verdicts_and_by_today(
    triage_judged, written, today, message
):
    spec = triage_spec(written=written)
    entries = [
        _dated(RULED, WRITTEN_ON),
        _dated((MOCK_TRIAGE_ITEM["scenario_id"], MOCK_TRIAGE_ITEM["variable"]), None)
        if triage_judged is None
        else _dated(
            (MOCK_TRIAGE_ITEM["scenario_id"], MOCK_TRIAGE_ITEM["variable"]),
            triage_judged,
        ),
    ]
    if message is None:
        driver.verify_written_days(entries, spec, today=today)
    else:
        with pytest.raises(SystemExit, match=message):
            driver.verify_written_days(entries, spec, today=today)


def test_a_ruled_entry_without_a_verdict_day_is_refused():
    spec = filled_spec()
    with pytest.raises(SystemExit, match="names no day"):
        driver.verify_written_days([_dated(RULED, None)], spec)
    with pytest.raises(SystemExit, match="names no day"):
        driver.verify_written_days([_dated(RULED, "[LEAD: day]")], spec)


@pytest.fixture
def adjudication_stage(stage, filled, monkeypatch):
    """The base's adjudication record staged, and a MOCK judged case for the
    ruled output: a MOCK verdict that lists the new model among its MOCK
    wrong models, judged by Opus 5.5 on v2. Today's UTC date is the MOCK
    written day, so no test here depends on the clock."""
    from policybench.judge_template import template_header

    monkeypatch.setattr(driver, "utc_today", lambda: WRITTEN_ON)
    annotations = stage / "publish" / RUN / "annotations"
    annotations.mkdir(parents=True)
    path = annotations / driver.ADJUDICATIONS
    path.write_bytes(base_blob(ANNOTATIONS_PATH / driver.ADJUDICATIONS))
    case = stage / "audit/cases" / f"us__{RULED[0]}__{RULED[1]}"
    case.mkdir(parents=True)
    (case / "prompt.md").write_text(template_header(2) + "\nMOCK question.\n")
    write_verdict(case, _verdict([NEW]))
    return stage, path


def test_adjudicate_exclusions_decides_the_ruled_output_once(adjudication_stage):
    stage, path = adjudication_stage
    args = SimpleNamespace(stage_dir=stage)
    driver.adjudicate_exclusions(args)
    text = path.read_text()
    record = json.loads(text)
    base = driver.base_adjudication_record()
    assert record["adjudications"][:-1] == base["adjudications"]
    entry = record["adjudications"][-1]
    assert driver.spec_key(entry) == RULED
    assert list(entry) == list(release_20261006.ENTRY_FIELDS)
    assert entry["excluded_from_scoring"] is True
    assert (entry["adjudicated_on"], entry["adjudicator"]) == (
        "2026-11-01",
        "developer",
    )
    assert (entry["adjudicated_failure_source"], entry["reference_verdict"]) == (
        "prompt_ambiguity",
        "unlisted_input",
    )
    assert entry["reference_basis"] == (
        "a qualifying Certificate of Rent Paid (mn_renters_credit_qualifying_crp)"
    )
    assert entry["judge_model"] == driver.JUDGE_MODEL
    assert WAVE_SENTENCE in record["date_conventions"]
    driver.verify_record_form(text, base, driver.decision_wave(driver.triage_items()))
    with pytest.raises(SystemExit, match="already decided"):
        driver.adjudicate_exclusions(args)


def test_the_record_gate_refuses_an_edited_note(adjudication_stage):
    stage, path = adjudication_stage
    driver.adjudicate_exclusions(SimpleNamespace(stage_dir=stage))
    record = json.loads(path.read_text())
    record["note"] = record.get("note", "") + " Edited."
    with pytest.raises(SystemExit, match="changes its note, schema or date"):
        driver.verify_record_form(
            driver.record_text(record), driver.base_adjudication_record()
        )


@pytest.mark.parametrize(
    "written, today, message",
    [
        ("2026-11-01", WRITTEN_ON, "precedes the day of a verdict"),
        ("2026-11-09", WRITTEN_ON, "precedes the day of a verdict"),
        ("2026-11-11", WRITTEN_ON, "falls after today's UTC date"),
        (WRITTEN_ON, "2026-11-09", "falls after today's UTC date"),
    ],
)
def test_adjudicate_exclusions_refuses_a_written_day_the_record_would_misstate(
    adjudication_stage, monkeypatch, written, today, message
):
    """Review r1, E F4. The MOCK ruled verdict is judged 2026-11-10. Before
    M16 each of these days passed: the step checked only that the written day
    is a real day on or after the ruling's (2026-11-01). It writes nothing."""
    stage, path = adjudication_stage
    spec = filled_spec(adjudications_written_on=written)
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    monkeypatch.setattr(driver, "utc_today", lambda: today)
    before = path.read_bytes()
    with pytest.raises(SystemExit, match=message):
        driver.adjudicate_exclusions(SimpleNamespace(stage_dir=stage))
    assert path.read_bytes() == before


@pytest.mark.parametrize("today", [WRITTEN_ON, "2026-12-01"])
def test_adjudicate_exclusions_takes_the_verdicts_day_up_to_today(
    adjudication_stage, monkeypatch, today
):
    stage, path = adjudication_stage
    monkeypatch.setattr(driver, "utc_today", lambda: today)
    driver.adjudicate_exclusions(SimpleNamespace(stage_dir=stage))
    record = json.loads(path.read_text())
    assert record["adjudications"][-1]["judged_on_utc"] == WRITTEN_ON
    assert WAVE_SENTENCE in record["date_conventions"]


# --- The ruled-entry gate at triage and the freeze (review r1, M3) -----------
#
# Haiku 5.5's tests of ruled_adjudication_problems, ported to the d2180 entry.
# The entry carries a MOCK bound verdict's judge fields, and every recorded
# decision gets a MOCK bound verdict that agrees with its judge fields, as
# verify_adjudications_keep_judge_verdicts requires.

RULED_CASE = f"us__{RULED[0]}__{RULED[1]}"
DECIDED_AT = "2026-10-27T02:00:00+00:00"
JSON_VALUES = st.recursive(
    st.none() | st.booleans() | st.integers() | st.text(max_size=8),
    lambda children: (
        st.lists(children, max_size=3)
        | st.dictionaries(st.text(max_size=5), children, max_size=3)
    ),
    max_leaves=6,
)


def _decided_verdicts(cases: Path, entries) -> Path:
    """A MOCK bound verdict for each recorded decision whose case has none,
    agreeing with the decision's judge fields."""
    for entry in entries:
        case = cases / driver.case_id(entry)
        if (case / "verdict.json").is_file():
            continue
        case.mkdir(parents=True, exist_ok=True)
        verdict = _verdict([], source=entry["judge_failure_source"])
        verdict["case_failure_subtype"] = entry["judge_failure_subtype"]
        verdict["reference_suspect"] = bool(entry.get("judge_reference_suspect"))
        write_verdict(case, verdict, judged_at_utc=DECIDED_AT)
    return cases


@pytest.fixture
def ruled(adjudication_stage):
    """Release 20261027's record and the record --step adjudicate-exclusions
    writes from it, both keyed by case, with the stage's cases directory."""
    from policybench.adjudications import parse_adjudications

    stage, path = adjudication_stage
    driver.adjudicate_exclusions(SimpleNamespace(stage_dir=stage))
    text = path.read_text()
    staged = json.loads(text)
    entries = parse_adjudications(copy.deepcopy(staged), path)
    cases = _decided_verdicts(stage / "audit" / "cases", entries)
    base = driver.base_adjudication_record()
    return SimpleNamespace(
        stage=stage,
        path=path,
        text=text,
        staged=staged,
        base=base,
        entries=entries,
        cases=cases,
        before={driver.case_id(e): e for e in base["adjudications"]},
        after={driver.case_id(e): e for e in entries},
    )


def test_the_ruled_record_appends_one_entry_and_keeps_every_base_entry(ruled):
    """64 decisions, 50 of them exclusions: every release 20261027 entry keeps
    its bytes and place, the d2180 entry follows them, and the top level
    changes only in its date conventions."""
    base, staged = ruled.base, ruled.staged
    entries = staged["adjudications"]
    assert len(base["adjudications"]) == 63
    assert len(entries) == 64
    assert sum(bool(e.get("excluded_from_scoring")) for e in entries) == 50
    for index, entry in enumerate(base["adjudications"]):
        assert json.dumps(entries[index]) == json.dumps(entry)
    assert driver.case_id(entries[-1]) == RULED_CASE
    assert list(staged) == list(base)
    assert {
        k: v
        for k, v in staged.items()
        if k not in ("adjudications", "date_conventions")
    } == {
        k: v for k, v in base.items() if k not in ("adjudications", "date_conventions")
    }
    assert staged["date_conventions"] == driver.release_date_conventions(
        base["date_conventions"]
    )


def test_the_adjudications_exclude_exactly_the_release_records_outputs(ruled):
    """Triage's requirement: the decided record excludes exactly the 50
    outputs the release's exclusion record lists."""
    from policybench.adjudications import excluded_case_keys
    from policybench.reference_exclusions import exclusion_keys

    released = release_record()["exclusions"]
    assert excluded_case_keys(ruled.entries) == exclusion_keys(released)
    assert len(exclusion_keys(released)) == 50
    assert excluded_case_keys(ruled.base["adjudications"]) != exclusion_keys(released)


def test_the_ruled_gate_passes_the_exact_built_entry(ruled):
    assert (
        driver.ruled_adjudication_problems(ruled.before, ruled.after, ruled.cases) == []
    )


def _swap_fields(entry: dict, index: int) -> dict:
    names = list(entry)
    a = index % (len(names) - 1)
    names[a], names[a + 1] = names[a + 1], names[a]
    return {name: entry[name] for name in names}


@settings(
    max_examples=120,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(kind=st.sampled_from(["value", "order", "extra", "drop"]), data=st.data())
def test_a_ruled_entry_edited_by_hand_is_refused(ruled, kind, data):
    """Any edit to the d2180 entry is refused: a value, the key order, an
    added or a dropped field. The entry is new, so the gate holds its judge
    fields to its bound verdict as well."""
    after = copy.deepcopy(ruled.after)
    entry = after[RULED_CASE]
    if kind == "value":
        name = data.draw(st.sampled_from(list(entry)))
        value = data.draw(JSON_VALUES)
        assume(json.dumps(value) != json.dumps(entry[name]))
        entry[name] = value
    elif kind == "order":
        after[RULED_CASE] = _swap_fields(entry, data.draw(st.integers(0, 40)))
    elif kind == "extra":
        name = data.draw(st.from_regex(r"x_[a-z]{1,6}", fullmatch=True))
        entry[name] = data.draw(JSON_VALUES)
    else:
        del entry[data.draw(st.sampled_from(list(entry)))]
    assert driver.ruled_adjudication_problems(ruled.before, after, ruled.cases) == [
        f"{RULED_CASE}: differs from the ruling's entry"
    ]


def test_a_ruled_entry_that_is_missing_is_refused(ruled):
    after = {k: v for k, v in ruled.after.items() if k != RULED_CASE}
    assert driver.ruled_adjudication_problems(ruled.before, after, ruled.cases) == [
        f"{RULED_CASE}: no staged decision"
    ]


# Edits to the d2180 entry that parse_adjudications accepts, so only the
# ruled-entry gate stands between them and the record.
RULED_EDITS = {
    "the judge's subtype as the decision's": (
        "adjudicated_failure_subtype",
        "credit_phaseout",
    ),
    "a reworded reasoning": ("reasoning", None),
    "another reference basis": ("reference_basis", "a MOCK basis"),
    "another decision day": ("adjudicated_on", "2026-11-02"),
    "another adjudicator": ("adjudicator", "MOCK adjudicator"),
    "another judge": ("judge_model", "claude-opus-5"),
    "another judge source": ("judge_failure_source", "prompt_ambiguity"),
    "another judge subtype": ("judge_failure_subtype", "credit_phaseout"),
    "a judge flag the verdict lacks": ("judge_reference_suspect", True),
    "another judged day": ("judged_on_utc", "2026-11-09"),
}
# Edits parse_adjudications refuses on its own; the gate refuses them too.
UNPARSED_RULED_EDITS = {
    "a scored decision": ("excluded_from_scoring", False),
    "another reference verdict": ("reference_verdict", "engine_defect"),
    "another decision source": ("adjudicated_failure_source", "llm_error"),
}


def _edited(record: dict, name: str, value) -> dict:
    record = copy.deepcopy(record)
    entry = next(e for e in record["adjudications"] if driver.case_id(e) == RULED_CASE)
    entry[name] = entry[name] + " MOCK edit." if value is None else value
    return record


@pytest.mark.parametrize(
    "name, value",
    list(RULED_EDITS.values()) + list(UNPARSED_RULED_EDITS.values()),
    ids=list(RULED_EDITS) + list(UNPARSED_RULED_EDITS),
)
def test_the_ruled_gate_refuses_each_field_edited(ruled, name, value):
    record = _edited(ruled.staged, name, value)
    after = {driver.case_id(e): e for e in record["adjudications"]}
    assert driver.ruled_adjudication_problems(ruled.before, after, ruled.cases) == [
        f"{RULED_CASE}: differs from the ruling's entry"
    ]


@pytest.mark.parametrize("rejudged", [frozenset({RULED_CASE}), frozenset()])
@pytest.mark.parametrize(
    "name, value", list(RULED_EDITS.values()), ids=list(RULED_EDITS)
)
def test_triages_record_gate_refuses_a_ruled_entry_edited_after_the_step(
    ruled, rejudged, name, value
):
    ruled.path.write_text(driver.record_text(_edited(ruled.staged, name, value)))
    with pytest.raises(SystemExit, match="Staged adjudications of the ruled outputs"):
        driver.stage_adjudications(ruled.path, rejudged, [], ruled.cases)


@pytest.mark.parametrize("rejudged", [frozenset({RULED_CASE}), frozenset()])
def test_triages_record_gate_passes_the_steps_record(ruled, rejudged):
    entries = driver.stage_adjudications(ruled.path, rejudged, [], ruled.cases)
    assert [driver.case_id(e) for e in entries] == list(ruled.after)
    assert ruled.path.read_text() == ruled.text


def _restaged(ruled, edit) -> None:
    record = copy.deepcopy(ruled.staged)
    edit(record["adjudications"])
    ruled.path.write_text(driver.record_text(record))


def _other_subtype(entry: dict) -> str:
    current = entry["adjudicated_failure_subtype"]
    return "credit_phaseout" if current != "credit_phaseout" else "thresholds_rates"


def _added(entries: list) -> None:
    extra = copy.deepcopy(entries[0])
    extra["scenario_id"] = "scenario_999"
    entries.insert(len(entries) - 1, extra)


BASE_DECISION_EDITS = {
    "a reworded reasoning": (
        lambda entries: entries[0].update(reasoning=entries[0]["reasoning"] + " X."),
        "change recorded decisions beyond",
    ),
    "another decision subtype": (
        lambda entries: entries[5].update(
            adjudicated_failure_subtype=_other_subtype(entries[5])
        ),
        "change recorded decisions beyond",
    ),
    "a dropped decision": (lambda entries: entries.pop(3), "drop recorded decisions"),
    "two decisions swapped": (
        lambda entries: entries.insert(1, entries.pop(0)),
        "change the committed entry order",
    ),
    "a decision on a case no new model re-opened": (
        _added,
        "add decisions on cases no new model re-opened",
    ),
}


@pytest.mark.parametrize(
    "edit, message", list(BASE_DECISION_EDITS.values()), ids=list(BASE_DECISION_EDITS)
)
def test_triages_record_gate_refuses_a_changed_base_decision(ruled, edit, message):
    _restaged(ruled, edit)
    with pytest.raises(SystemExit, match=message):
        driver.stage_adjudications(ruled.path, frozenset({RULED_CASE}), [], ruled.cases)


def test_a_reopened_case_keeps_its_decision_fields(ruled):
    """A case the new model re-opened may move only its judge fields."""
    first = driver.case_id(ruled.staged["adjudications"][0])
    _restaged(ruled, lambda entries: entries[0].update(adjudicated_on="2026-11-02"))
    with pytest.raises(SystemExit, match="change recorded decisions beyond"):
        driver.stage_adjudications(
            ruled.path, frozenset({RULED_CASE, first}), [], ruled.cases
        )


def test_a_decision_the_spec_does_not_list_is_refused_on_a_reopened_case(ruled):
    _restaged(ruled, _added)
    extra = driver.case_id(
        {**ruled.staged["adjudications"][0], "scenario_id": "scenario_999"}
    )
    with pytest.raises(SystemExit, match="add decisions the spec does not list"):
        driver.stage_adjudications(
            ruled.path, frozenset({RULED_CASE, extra}), [], ruled.cases
        )


def test_the_freezes_record_gate_runs_triages_gates_unstubbed(ruled, tmp_path):
    """freeze_fable52.verify_adjudication_record on the step's record and the
    release's exclusion record: it passes, and refuses the d2180 entry edited
    after the step and a record that still excludes only the base's outputs."""
    import freeze_fable52 as release

    source_us = tmp_path / "source-us"
    source_us.mkdir()
    (source_us / EXCLUSIONS_NAME).write_text(release_text())
    rejudged = frozenset({RULED_CASE})
    assert (
        release.verify_adjudication_record(
            ruled.path, source_us, rejudged, [], ruled.cases
        )
        == 0
    )
    edited = _edited(ruled.staged, "adjudicated_failure_subtype", "credit_phaseout")
    ruled.path.write_text(driver.record_text(edited))
    with pytest.raises(SystemExit, match="Staged adjudications of the ruled outputs"):
        release.verify_adjudication_record(
            ruled.path, source_us, rejudged, [], ruled.cases
        )
    ruled.path.write_text(ruled.text)
    (source_us / EXCLUSIONS_NAME).write_text(driver.exclusions_text(base_record()))
    with pytest.raises(SystemExit, match="the staged exclusion record disagree"):
        release.verify_adjudication_record(
            ruled.path, source_us, rejudged, [], ruled.cases
        )


@pytest.mark.parametrize(
    "adjudications",
    [
        pytest.param(lambda item: [], id="no adjudication for the record"),
        pytest.param(lambda item: [item, item], id="the record decided twice"),
        pytest.param(
            lambda item: [item, {**item, "variable": "state_income_tax"}],
            id="an adjudication with no record",
        ),
    ],
)
def test_the_spec_must_decide_each_record_exactly_once(
    adjudication_stage, monkeypatch, adjudications
):
    stage, path = adjudication_stage
    item = filled_spec()["adjudications"][0]
    spec = filled_spec(adjudications=adjudications(item))
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    with pytest.raises(SystemExit, match="name different outputs"):
        driver.exclusion_adjudications(
            driver.base_adjudication_record(), stage / "audit" / "cases"
        )


def test_the_spec_must_restate_exactly_the_ruled_outputs_already_decided(
    adjudication_stage, monkeypatch
):
    stage, path = adjudication_stage
    item = filled_spec()["adjudications"][0]
    spec = filled_spec(restated_adjudications=[item])
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    with pytest.raises(SystemExit, match="differ from the spec's restated list"):
        driver.exclusion_adjudications(
            driver.base_adjudication_record(), stage / "audit" / "cases"
        )


# Review r3, Q1: release 20261027's two committed annotation files, and the
# MOCK stand-ins the triage and unit tests below serve in their place.
ANNOTATION_CSVS = ("us_audit_row_annotations.csv", "us_case_notes.csv")
PLURAL = {
    "case_failure_source": "case_failure_sources",
    "case_failure_subtype": "case_failure_subtypes",
}
MOCK_PUBLISHED_ROW = "MOCK: the row annotation as release 20261027 published it."
MOCK_PUBLISHED_NOTE = "MOCK: the case note as release 20261027 published it."
PARSE_NOTE = "All wrong responses were missing or unparseable predictions."


def _case_ids(frame) -> list[str]:
    return [
        f"{country}__{scenario}__{variable}"
        for country, scenario, variable in zip(
            frame.country, frame.scenario_id, frame.variable, strict=True
        )
    ]


def _on(frame, case: str):
    """``frame``'s rows on ``case`` (an audit case id)."""
    return frame[[found == case for found in _case_ids(frame)]]


def _mock_base_files(rows, cases, decisions, amended=None) -> dict[str, bytes]:
    """MOCK: release 20261027's two committed annotation files, built from
    MOCK collected frames (collect_audit's columns) as its triage wrote them:
    one MOCK committed amendment rewords case ``amended``'s row annotations
    and case note, then ``decisions`` apply."""
    from policybench.adjudications import apply_adjudications

    rows, cases = rows.copy(), cases.rename(columns=PLURAL).copy()
    rows.loc[[c == amended for c in _case_ids(rows)], "annotation"] = MOCK_PUBLISHED_ROW
    cases.loc[[c == amended for c in _case_ids(cases)], "case_annotation"] = (
        MOCK_PUBLISHED_NOTE
    )
    rows, cases, _ = apply_adjudications(rows, cases, decisions)
    return {
        name: frame.to_csv(index=False).encode()
        for name, frame in zip(ANNOTATION_CSVS, (rows, cases), strict=True)
    }


def _serve_mock_base(monkeypatch, state, decisions=None) -> None:
    """driver.base_commit_blob with release 20261027's two committed
    annotation files built at each read from ``state.base`` (MOCK collected
    frames) and ``state.amended`` (_mock_base_files), with its decisions
    (release 20261027's, unless ``decisions`` names others), and every other
    path from git."""
    decisions = driver.base_adjudications() if decisions is None else decisions

    def blob(path):
        path = Path(path)
        if path.parent == ANNOTATIONS_PATH and path.name in ANNOTATION_CSVS:
            files = _mock_base_files(*state.base, decisions, state.amended)
            return files[path.name]
        return base_blob(path)

    monkeypatch.setattr(driver, "base_commit_blob", blob)


# Terra's triage_stage tests, ported: driver.triage itself on the stage after
# --step adjudicate-exclusions, with MOCK collected annotations.


@pytest.fixture
def triage_stage(ruled, monkeypatch):
    """The stage after the adjudicate step, ready for triage: the release's
    exclusion record installed, the ruled case re-opened, and MOCK collected
    annotations with one MOCK wrong row for each decided case."""
    import policybench.audit

    stage = ruled.stage
    bundle = stage / "publish" / RUN
    (bundle / "us" / EXCLUSIONS_NAME).write_text(release_text())
    state = SimpleNamespace(pending=[], missing=pd.DataFrame(), hedged=pd.DataFrame())

    def reopen(*cases):
        (stage / driver.PROMPT_CHANGES).write_text(
            json.dumps({"added": [], "changed": [RULED_CASE, *cases], "kept": []})
        )

    reopen()
    monkeypatch.setattr(driver, "validate_verdicts", lambda *a, **kw: state.pending)
    monkeypatch.setattr(driver, "load_seed", lambda stage: {})
    monkeypatch.setattr(driver, "stage_upgrade", lambda stage: None)
    keys = [
        {name: entry[name] for name in ("country", "scenario_id", "variable")}
        for entry in ruled.entries
    ]
    state.rows = pd.DataFrame(
        [
            {
                **key,
                "model": NEW if driver.case_id(key) == RULED_CASE else "incumbent-a",
                "failure_source": "llm_error",
                "failure_subtype": "thresholds_rates",
                "reference_suspect": False,
                "annotation": "MOCK row note.",
            }
            for key in keys
        ]
    )
    state.cases = pd.DataFrame(
        [
            {
                **key,
                "reference_suspect": False,
                "wrong_model_count": 1,
                "case_failure_source": "llm_error",
                "case_failure_subtype": "thresholds_rates",
                "reference_bug_hypothesis": "",
                "case_annotation": "MOCK case note.",
            }
            for key in keys
        ]
    )
    monkeypatch.setattr(
        policybench.audit,
        "collect_audit",
        lambda *a, **kw: {
            "missing": state.missing,
            "hedged": state.hedged,
            "row": state.rows.copy(),
            "case": state.cases.copy(),
        },
    )
    # MOCK: release 20261027's two committed annotation files. They hold the
    # 63 cases its record decides (on the MOCK board the ruled case is the
    # new model's alone, so they lack it) as its triage wrote them, its
    # decisions applied, and one MOCK committed amendment rewords the first
    # decided case's row annotation and case note (review r3, Q1).
    kept = [driver.case_id(key) != RULED_CASE for key in keys]
    state.base = (state.rows[kept].copy(), state.cases[kept].copy())
    state.amended = driver.case_id(ruled.base["adjudications"][0])
    _serve_mock_base(monkeypatch, state)

    def run():
        driver.triage(SimpleNamespace(stage_dir=stage), bundle)

    return SimpleNamespace(
        stage=stage,
        bundle=bundle,
        record=ruled.path,
        text=ruled.text,
        staged=ruled.staged,
        state=state,
        reopen=reopen,
        run=run,
    )


def test_triage_accepts_the_steps_record_unchanged(triage_stage, capsys):
    triage_stage.run()
    assert triage_stage.record.read_text() == triage_stage.text
    assert "Triage complete: 64 rows / 64 cases" in capsys.readouterr().out
    annotations = triage_stage.bundle / "annotations"
    notes = pd.read_csv(annotations / "us_case_notes.csv")
    note = notes[(notes.scenario_id == RULED[0]) & (notes.variable == RULED[1])]
    assert note[["case_failure_sources", "case_failure_subtypes"]].values.tolist() == [
        ["prompt_ambiguity", "state_local_rule"]
    ]
    assert pd.read_csv(triage_stage.stage / "unresolved-rows.csv").empty
    assert pd.read_csv(triage_stage.stage / "reference-flags.csv").empty


def test_triage_refuses_exclusions_the_decisions_do_not_make(triage_stage):
    us = triage_stage.bundle / "us" / EXCLUSIONS_NAME
    us.write_text(driver.exclusions_text(base_record()))
    with pytest.raises(SystemExit, match="adjudication exclusions differ"):
        triage_stage.run()


def _first_case(triage_stage) -> str:
    return driver.case_id(triage_stage.staged["adjudications"][0])


def _extra_case(triage_stage) -> str:
    first = triage_stage.staged["adjudications"][0]
    return driver.case_id({**first, "scenario_id": "scenario_999"})


def _judge_subtype_by_hand(record: dict) -> None:
    entry = record["adjudications"][0]
    entry["judge_failure_subtype"] = (
        "credit_phaseout"
        if entry["judge_failure_subtype"] != "credit_phaseout"
        else "thresholds_rates"
    )


TRIAGE_REFUSALS = {
    "a decision the spec does not list": (
        lambda record: _added(record["adjudications"]),
        _extra_case,
        "add decisions the spec does not list",
    ),
    "judge fields written by hand": (
        _judge_subtype_by_hand,
        _first_case,
        "not restated by the restate script",
    ),
    "another change to a recorded decision": (
        lambda record: record["adjudications"][0].update(
            reasoning=record["adjudications"][0]["reasoning"] + " X."
        ),
        None,
        "change recorded decisions beyond",
    ),
    "a dropped decision": (
        lambda record: record["adjudications"].pop(3),
        None,
        "drop recorded decisions",
    ),
    "an edited date convention": (
        lambda record: record.update(
            date_conventions=record["date_conventions"] + " MOCK."
        ),
        None,
        "beyond naming this release's waves",
    ),
    "the ruled entry edited after the step": (
        lambda record: record["adjudications"][-1].update(
            reasoning=record["adjudications"][-1]["reasoning"] + " X."
        ),
        None,
        "Staged adjudications of the ruled outputs",
    ),
}


@pytest.mark.parametrize(
    "edit, reopened, message",
    list(TRIAGE_REFUSALS.values()),
    ids=list(TRIAGE_REFUSALS),
)
def test_triage_refuses_a_record_changed_without_a_reason(
    triage_stage, edit, reopened, message
):
    record = copy.deepcopy(triage_stage.staged)
    edit(record)
    triage_stage.record.write_text(driver.record_text(record))
    if reopened is not None:
        triage_stage.reopen(reopened(triage_stage))
    with pytest.raises(SystemExit, match=message):
        triage_stage.run()


def test_triage_refuses_bytes_the_entry_gate_cannot_see(triage_stage):
    first = '"country": "us",'
    assert first in triage_stage.text
    doubled = triage_stage.text.replace(first, first + "\n      " + first, 1)
    triage_stage.record.write_text(doubled)
    with pytest.raises(SystemExit, match="not in the committed form"):
        triage_stage.run()


def test_triage_stops_on_a_pending_verdict(triage_stage):
    triage_stage.state.pending = ["MOCK pending case"]
    with pytest.raises(SystemExit, match="missing or invalid verdicts; run judge"):
        triage_stage.run()


@pytest.mark.parametrize("frame", ["missing", "hedged"])
def test_triage_stops_on_a_missing_or_hedged_verdict(triage_stage, frame):
    setattr(triage_stage.state, frame, pd.DataFrame([{"case_id": RULED_CASE}]))
    with pytest.raises(SystemExit, match="missing/hedged audit; run judge"):
        triage_stage.run()


def test_triage_stops_when_a_case_miscounts_its_rows(triage_stage):
    triage_stage.state.cases.loc[0, "wrong_model_count"] = 2
    with pytest.raises(SystemExit, match="wrong_model_count disagrees"):
        triage_stage.run()


# --- Kept cases carry release 20261027's wording (review r3, Q1) -------------
#
# Triage gives every case it keeps the row annotations and case note release
# 20261027 published, beside this release's decisions (carry_kept_wording),
# and stops before it writes when a kept case's rows or note differ from that
# release's files (verify_kept_annotations). Here the files are MOCK
# (triage_stage's state.base), and a MOCK committed amendment rewords one case.


def _written(triage_stage) -> tuple:
    annotations = triage_stage.bundle / "annotations"
    return tuple(
        pd.read_csv(annotations / name, keep_default_na=False)
        for name in ANNOTATION_CSVS
    )


def test_triage_carries_a_kept_cases_published_wording(triage_stage):
    """On the MOCK board triage writes the MOCK published row annotation and
    case note on the kept case the MOCK committed amendment rewords, the
    case's decision applied again, and keeps the collected text on the ruled
    case, which the stage re-opened. Every kept case's rows and note are
    release 20261027's files' (MOCK) byte for byte."""
    triage_stage.run()
    rows, notes = _written(triage_stage)
    amended = triage_stage.state.amended
    assert _on(rows, amended).annotation.tolist() == [MOCK_PUBLISHED_ROW]
    (note,) = _on(notes, amended).case_annotation
    assert note.startswith(MOCK_PUBLISHED_NOTE + " Developer adjudication (")
    assert _on(rows, RULED_CASE).annotation.tolist() == ["MOCK row note."]
    (ruled_note,) = _on(notes, RULED_CASE).case_annotation
    assert ruled_note.startswith("MOCK case note. Developer adjudication (2026-11-01)")
    files = _mock_base_files(
        *triage_stage.state.base, driver.base_adjudications(), amended
    )
    for name, written in zip(ANNOTATION_CSVS, (rows, notes), strict=True):
        kept = written[[case != RULED_CASE for case in _case_ids(written)]]
        assert kept.to_csv(index=False).encode() == files[name]


def _second_decided(triage_stage) -> str:
    """A kept case the stage's record decides and the MOCK amendment does
    not reword."""
    return next(
        case
        for case in map(driver.case_id, triage_stage.staged["adjudications"])
        if case not in (RULED_CASE, triage_stage.state.amended)
    )


def _add_kept_case(state, scenario: str, source: str, subtype: str) -> tuple:
    """Give the MOCK board a case release 20261027's files (MOCK) hold and no
    record decides: one incumbent's wrong row, the files' text in the base
    and collect_audit's (MOCK) in the stage. Returns the stage's row and
    note."""
    case = {"country": "us", "scenario_id": scenario, "variable": "snap"}
    row = {
        **case,
        "model": "incumbent-a",
        "failure_source": source,
        "failure_subtype": subtype,
        "reference_suspect": False,
        "annotation": "MOCK row note.",
    }
    note = {
        **case,
        "reference_suspect": False,
        "wrong_model_count": 1,
        "case_failure_source": source,
        "case_failure_subtype": subtype,
        "reference_bug_hypothesis": "",
        "case_annotation": "MOCK case note.",
    }
    base_rows, base_notes = state.base
    published_row = {**row, "annotation": MOCK_PUBLISHED_ROW}
    published_note = {**note, "case_annotation": MOCK_PUBLISHED_NOTE}
    state.base = (
        pd.concat([base_rows, pd.DataFrame([published_row])], ignore_index=True),
        pd.concat([base_notes, pd.DataFrame([published_note])], ignore_index=True),
    )
    state.rows = pd.concat([state.rows, pd.DataFrame([row])], ignore_index=True)
    state.cases = pd.concat([state.cases, pd.DataFrame([note])], ignore_index=True)
    return row, note


def _edit_row_class(triage_stage) -> list[str]:
    state = triage_stage.state
    _add_kept_case(state, "scenario_997", "llm_error", "thresholds_rates")
    state.rows.loc[state.rows.index[-1], "failure_subtype"] = "credit_phaseout"
    return ["us__scenario_997__snap incumbent-a failure_subtype"]


def _edit_hypothesis(triage_stage) -> list[str]:
    state, case = triage_stage.state, _second_decided(triage_stage)
    state.cases.loc[_on(state.cases, case).index[0], "reference_bug_hypothesis"] = (
        "MOCK: a hypothesis release 20261027 did not publish."
    )
    return [f"{case} case note reference_bug_hypothesis"]


def _add_incumbent_row(triage_stage) -> list[str]:
    state, case = triage_stage.state, _second_decided(triage_stage)
    row = _on(state.rows, case).iloc[0].to_dict()
    extra = pd.DataFrame([{**row, "model": "incumbent-b"}])
    state.rows = pd.concat([state.rows, extra], ignore_index=True)
    state.cases.loc[_on(state.cases, case).index[0], "wrong_model_count"] = 2
    return [
        f"{case} incumbent-b: a row release 20261027 does not hold",
        f"{case} case note wrong_model_count",
    ]


@pytest.mark.parametrize(
    "edit",
    [_edit_row_class, _edit_hypothesis, _add_incumbent_row],
    ids=["a row's class", "the note's hypothesis", "a row the base lacks"],
)
def test_triage_stops_before_it_writes_on_a_kept_case_off_release_20261027s(
    triage_stage, edit
):
    """MOCK edits to a kept case's collected frames (a row's class on a case
    no record decides; the note's hypothesis, and an incumbent's row release
    20261027's files lack, on a decided one) stop triage at the kept-case
    gate, which names each cell, before it writes either annotation file."""
    annotations = triage_stage.bundle / "annotations"

    def files():
        return {
            name: (annotations / name).read_bytes()
            for name in ANNOTATION_CSVS
            if (annotations / name).is_file()
        }

    before = files()
    expected = edit(triage_stage)
    with pytest.raises(
        SystemExit, match="a case this release keeps must carry"
    ) as refused:
        triage_stage.run()
    assert str(refused.value).endswith(f"these differ: {expected}")
    assert files() == before


def test_triage_keeps_a_new_models_row_on_a_kept_parse_failure_only_case(
    triage_stage, capsys
):
    """On the MOCK board the new model joins a parse-failure-only case the
    release keeps, which no prompt re-opens: release 20261027's files (MOCK)
    hold the incumbent's row, and the stage holds it and the new model's.
    Triage passes; the incumbent's row and the case note take the files'
    text, the new model's row keeps the text collect_audit built, and the
    note counts both rows."""
    state = triage_stage.state
    row, _ = _add_kept_case(
        state, "scenario_998", "parse_contract_failure", "missing_output"
    )
    joined = {
        **row,
        "model": NEW,
        "annotation": "MOCK: the new model's row as collect_audit built it.",
    }
    state.rows = pd.concat([state.rows, pd.DataFrame([joined])], ignore_index=True)
    state.cases.loc[state.cases.index[-1], "wrong_model_count"] = 2
    triage_stage.run()
    assert "Triage complete: 66 rows / 65 cases" in capsys.readouterr().out
    rows, notes = _written(triage_stage)
    case = "us__scenario_998__snap"
    assert _on(rows, case).to_dict("records") == [
        {**row, "annotation": MOCK_PUBLISHED_ROW},
        joined,
    ]
    assert _on(notes, case)[
        ["wrong_model_count", "case_annotation"]
    ].values.tolist() == [[2, MOCK_PUBLISHED_NOTE]]


# The kept-case gate on MOCK frames: a judged case two incumbents answer wrong
# and a parse-failure-only case one does, collect_audit's columns, and MOCK
# release 20261027 files that hold both, the judged case's text reworded by a
# MOCK committed amendment and no decision.
GATE_JUDGED, GATE_PARSE = "us__scenario_901__snap", "us__scenario_902__snap"


def _gate_frames() -> tuple:
    def row(scenario, model, source, subtype, text):
        return {
            "country": "us",
            "scenario_id": scenario,
            "variable": "snap",
            "model": model,
            "failure_source": source,
            "failure_subtype": subtype,
            "reference_suspect": False,
            "annotation": text,
        }

    def note(scenario, count, source, subtype, text):
        return {
            "country": "us",
            "scenario_id": scenario,
            "variable": "snap",
            "wrong_model_count": count,
            "case_failure_source": source,
            "case_failure_subtype": subtype,
            "reference_suspect": False,
            "reference_bug_hypothesis": "",
            "case_annotation": text,
        }

    judged = ("prompt_ambiguity", "state_local_rule")
    parse = ("parse_contract_failure", "missing_output")
    rows = pd.DataFrame(
        [
            row("scenario_901", "incumbent-a", *judged, "MOCK diagnosis a."),
            row("scenario_901", "incumbent-b", *judged, "MOCK diagnosis b."),
            row("scenario_902", "incumbent-a", *parse, PARSE_NOTE),
        ]
    )
    cases = pd.DataFrame(
        [
            note("scenario_901", 2, *judged, "MOCK rationale."),
            note("scenario_902", 1, *parse, PARSE_NOTE),
        ]
    )
    return rows, cases


@pytest.fixture
def gate_base(monkeypatch):
    state = SimpleNamespace(base=_gate_frames(), amended=GATE_JUDGED)
    _serve_mock_base(monkeypatch, state, decisions=[])
    return state


def _built(rows, cases, rejudged=frozenset()):
    return driver.annotation_frames(
        {"row": rows, "case": cases}, frozenset(rejudged), [], []
    )


def test_the_carry_gives_kept_cases_the_published_text_by_row(gate_base):
    """carry_kept_wording on MOCK frames: a kept case's rows and note take
    the files' text, row by row; a re-opened case keeps the collected text;
    no other column moves."""
    rows, cases = _gate_frames()
    carried_rows, carried_cases = driver.carry_kept_wording(
        rows, cases.rename(columns=PLURAL), frozenset()
    )
    assert carried_rows.annotation.tolist() == [
        MOCK_PUBLISHED_ROW,
        MOCK_PUBLISHED_ROW,
        PARSE_NOTE,
    ]
    assert carried_cases.case_annotation.tolist() == [MOCK_PUBLISHED_NOTE, PARSE_NOTE]
    for carried, frame, column in (
        (carried_rows, rows, "annotation"),
        (carried_cases, cases.rename(columns=PLURAL), "case_annotation"),
    ):
        assert carried.drop(columns=column).equals(frame.drop(columns=column))
    reopened_rows, reopened_cases = driver.carry_kept_wording(
        rows, cases.rename(columns=PLURAL), frozenset({GATE_JUDGED})
    )
    assert reopened_rows.annotation.tolist() == rows.annotation.tolist()
    assert reopened_cases.case_annotation.tolist() == cases.case_annotation.tolist()
    assert rows.annotation.tolist()[0] == "MOCK diagnosis a."


def test_the_kept_gate_passes_the_built_frames_and_a_new_models_parse_row(
    gate_base,
):
    """The frames annotation_frames builds pass; so do they with the new
    model's row on the parse-failure-only case and the note counting it."""
    rows, cases = _gate_frames()
    assert driver.kept_annotation_problems(*_built(rows, cases), frozenset(), []) == []
    joined = rows.iloc[[2]].assign(model=NEW)
    rows = pd.concat([rows, joined], ignore_index=True)
    cases.loc[1, "wrong_model_count"] = 2
    assert driver.kept_annotation_problems(*_built(rows, cases), frozenset(), []) == []


def _uncarried(rows, cases):
    return rows, cases.rename(columns=PLURAL)


def _drop_row(rows, cases):
    rows, cases = _built(rows, cases)
    return rows.drop(index=1), cases


def _double_row(rows, cases):
    rows, cases = _built(rows, cases)
    return pd.concat([rows, rows.iloc[[0]]], ignore_index=True), cases


def _drop_note(rows, cases):
    rows, cases = _built(rows, cases)
    return rows, cases.drop(index=1)


def _extra_incumbent(rows, cases):
    rows, cases = _built(rows, cases)
    extra = rows.iloc[[2]].assign(model="incumbent-c")
    cases.loc[1, "wrong_model_count"] = 2
    return pd.concat([rows, extra], ignore_index=True), cases


def _uncounted_new_row(rows, cases):
    rows, cases = _built(rows, cases)
    return pd.concat([rows, rows.iloc[[2]].assign(model=NEW)], ignore_index=True), cases


def _reordered(rows, cases):
    rows, cases = _built(rows, cases)
    return rows[[*rows.columns[1:], rows.columns[0]]], cases


GATE_REFUSALS = {
    "the text collect_audit built": (
        _uncarried,
        [
            f"{GATE_JUDGED} incumbent-a annotation",
            f"{GATE_JUDGED} incumbent-b annotation",
            f"{GATE_JUDGED} case note case_annotation",
        ],
    ),
    "a row gone": (_drop_row, [f"{GATE_JUDGED} incumbent-b: 0 rows, not one"]),
    "a row twice": (_double_row, [f"{GATE_JUDGED} incumbent-a: 2 rows, not one"]),
    "a note gone": (_drop_note, [f"{GATE_PARSE} case note: 0 notes, not one"]),
    "an incumbent's row the base lacks": (
        _extra_incumbent,
        [
            f"{GATE_PARSE} incumbent-c: a row release 20261027 does not hold",
            f"{GATE_PARSE} case note wrong_model_count",
        ],
    ),
    "a new model's row the note does not count": (
        _uncounted_new_row,
        [f"{GATE_PARSE} case note wrong_model_count"],
    ),
    "a column out of place": (
        _reordered,
        [
            "the row annotations' columns ['scenario_id', 'variable', 'model', "
            "'failure_source', 'failure_subtype', 'reference_suspect', "
            "'annotation', 'country'] are not release 20261027's ['country', "
            "'scenario_id', 'variable', 'model', 'failure_source', "
            "'failure_subtype', 'reference_suspect', 'annotation']"
        ],
    ),
}


@pytest.mark.parametrize(
    "edit, expected", list(GATE_REFUSALS.values()), ids=list(GATE_REFUSALS)
)
def test_the_kept_gate_names_each_difference(gate_base, edit, expected):
    rows, cases = edit(*_gate_frames())
    assert driver.kept_annotation_problems(rows, cases, frozenset(), []) == expected
    with pytest.raises(SystemExit, match="a case this release keeps must carry"):
        driver.verify_kept_annotations(rows, cases, frozenset(), [])


def test_the_kept_gate_compares_no_reopened_case(gate_base):
    """The collected text on both MOCK cases, both re-opened: nothing to
    compare. One kept: only its cells."""
    rows, cases = _uncarried(*_gate_frames())
    both = frozenset({GATE_JUDGED, GATE_PARSE})
    assert driver.kept_annotation_problems(rows, cases, both, []) == []
    assert (
        driver.kept_annotation_problems(rows, cases, frozenset({GATE_PARSE}), [])
        == GATE_REFUSALS["the text collect_audit built"][1]
    )


NON_KEY_ROW_COLUMNS = (
    "failure_source",
    "failure_subtype",
    "reference_suspect",
    "annotation",
)
NON_KEY_NOTE_COLUMNS = (
    "wrong_model_count",
    "case_failure_sources",
    "case_failure_subtypes",
    "reference_suspect",
    "reference_bug_hypothesis",
    "case_annotation",
)


@settings(
    max_examples=80,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    frame=st.sampled_from(["row", "note"]),
    index=st.integers(0, 2),
    column=st.integers(0, 5),
    value=st.text(alphabet="MOCKxyz ", min_size=1, max_size=6),
    reopened=st.booleans(),
)
def test_any_one_cell_off_the_base_on_a_kept_case_is_named(
    gate_base, frame, index, column, value, reopened
):
    """Invariant: on the built MOCK frames, a single non-key cell set to any
    other value is named alone, as the gate names it, on a kept case, and
    passes on a re-opened one."""
    rows, cases = _built(*_gate_frames())
    target = rows if frame == "row" else cases
    names = NON_KEY_ROW_COLUMNS if frame == "row" else NON_KEY_NOTE_COLUMNS
    index %= len(target)
    name = names[column % len(names)]
    assume(str(target.loc[index, name]) != value)
    target[name] = target[name].astype(object)
    target.loc[index, name] = value
    case = _case_ids(target)[index]
    if frame == "row":
        expected = [f"{case} {target.loc[index, 'model']} {name}"]
    else:
        expected = [f"{case} case note {name}"]
    rejudged = frozenset({case}) if reopened else frozenset()
    found = driver.kept_annotation_problems(rows, cases, rejudged, [])
    assert found == ([] if reopened else expected)


# --- Check (a) with the ruled case kept, on release 20261027's data from git ---
# Review r2, N1.
#
# Triage applies d2180's decision to the ruled case whether or not the new
# model re-opened it. These tests apply the entry adjudicate-exclusions builds
# (its judge fields from the ruled fixture's MOCK verdict), beside release
# 20261027's decisions, to the frames triage builds (driver.annotation_frames)
# from text shaped like the seed's: release 20261027's committed annotations,
# read from git, with Terra's committed text amendments undone (review r3,
# Q1). They move release 20261027's own payload (from git) where the exporter
# writes those annotations, and read no prediction of the new model.

# Each annotation field of a cell, and the annotation frame and column the
# exporter writes it from (policybench.analysis.build_dashboard_payload, by
# way of policybench.full_run_export's loaders): the model's row annotation
# or the case note, the text stripped. A cell carries a field only when the
# exporter wrote it, which a decision does not change.
CELL_SOURCES = (
    ("annotation", "row", "annotation"),
    ("failureSource", "row", "failure_source"),
    ("failureSubtype", "row", "failure_subtype"),
    ("caseAnnotation", "case", "case_annotation"),
    ("caseFailureSources", "case", "case_failure_sources"),
    ("caseFailureSubtypes", "case", "case_failure_subtypes"),
)


@pytest.fixture(scope="module")
def base_live() -> dict:
    """Release 20261027's payload, from git (driver.base_payload_from_commit)."""
    return driver.base_payload_from_commit()


def base_annotation_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Release 20261027's row annotations and case notes, from git."""
    return (
        pd.read_csv(io.BytesIO(base_blob(ANNOTATIONS_PATH / name)))
        for name in ("us_audit_row_annotations.csv", "us_case_notes.csv")
    )


def exported_cells(cells: dict, rows, cases, key: tuple[str, str]) -> dict:
    """``cells`` (one output's, by model) with each annotation field a cell
    carries taken from the frames as the exporter writes it."""
    scenario, variable = key
    note = cases[(cases.scenario_id == scenario) & (cases.variable == variable)]
    assert len(note) == 1
    rows = rows[(rows.scenario_id == scenario) & (rows.variable == variable)]
    out = {}
    for model, cell in cells.items():
        row = rows[rows.model == model]
        assert len(row) <= 1
        frames = {"row": row.iloc[0] if len(row) else None, "case": note.iloc[0]}
        moved = dict(cell)
        for field, frame, column in CELL_SOURCES:
            if field in cell:
                assert frames[frame] is not None, (model, field)
                moved[field] = str(frames[frame][column]).strip()
        out[model] = moved
    return out


# Review r3, Q1: release 20261027's committed wording amendments, the last
# 1,578 of which (after the first 870) are Terra's, the ones that release
# publishes. The seed is not in the repository: undoing Terra's text
# amendments in reverse order on the committed files, and dropping each case
# note's adjudication sentence, rebuilds the text collect_audit gives the
# seed (the local test below checks it against the seed itself).
TERRA_AMENDMENTS_START = 870


@functools.cache
def _terra_amendments() -> tuple[dict, ...]:
    record = json.loads(base_blob(ANNOTATIONS_PATH / "us_wording-amendments.json"))
    assert len(record["amendments"]) == 2448
    assert (
        "The last 1578 (after the first 870) are for cases a new model re-opened"
        in record["note"]
    )
    return tuple(record["amendments"][TERRA_AMENDMENTS_START:])


@functools.cache
def _seed_shaped_text() -> tuple[str, str]:
    """Release 20261027's two committed files with Terra's text amendments
    undone, last first, and no adjudication sentence: CSV text in triage's
    column names."""
    from policybench.adjudications import _strip_adjudication_sentence

    rows, cases = (
        pd.read_csv(
            io.BytesIO(base_blob(ANNOTATIONS_PATH / name)), keep_default_na=False
        )
        for name in ("us_audit_row_annotations.csv", "us_case_notes.csv")
    )
    cases["case_annotation"] = [
        _strip_adjudication_sentence(note) for note in cases.case_annotation
    ]
    for item in reversed(_terra_amendments()):
        if item["field"] == "reasoning":
            continue
        frame = rows if item["field"] == "annotation" else cases
        found = [case == item["case_id"] for case in _case_ids(frame)]
        if item["field"] == "annotation":
            found = [a and m == item["model"] for a, m in zip(found, frame.model)]
        (index,) = frame.index[found]
        text = frame.at[index, item["field"]]
        assert text.count(item["new"]) == 1, item
        frame.at[index, item["field"]] = text.replace(item["new"], item["old"])
    return rows.to_csv(index=False), cases.to_csv(index=False)


def _seed_shaped() -> dict:
    """_seed_shaped_text as collect_audit returns its frames."""
    rows_text, cases_text = _seed_shaped_text()
    cases = pd.read_csv(io.StringIO(cases_text), keep_default_na=False)
    return {
        "row": pd.read_csv(io.StringIO(rows_text), keep_default_na=False),
        "case": cases.rename(columns={v: k for k, v in PLURAL.items()}),
    }


def decided_on_the_base(
    live: dict, entry: dict, rejudged: frozenset[str] = frozenset()
) -> tuple[dict, dict, list[str]]:
    """``live`` with the incumbents' cells on ``entry``'s output as the
    exporter writes them from the frames triage builds
    (driver.annotation_frames) from text shaped like the seed's
    (_seed_shaped_text), ``entry`` decided beside release 20261027's
    decisions and its case kept unless ``rejudged`` names it; the moved
    cells; the models whose cells moved. Release 20261027's committed frames
    first reproduce its own cells there, byte for byte, so the mapping is
    the exporter's on this output."""
    key = driver.spec_key(entry)
    us = live["countries"]["us"]
    incumbents = {row["model"] for row in us["modelStats"]}
    held = {
        model: cell
        for model, cell in us["scenarioPredictions"][key[0]][key[1]].items()
        if model in incumbents
    }
    rows, cases = base_annotation_frames()
    assert json.dumps(exported_cells(held, rows, cases, key)) == json.dumps(held)
    rows, cases = driver.annotation_frames(
        _seed_shaped(), frozenset(rejudged), [*driver.base_adjudications(), entry], []
    )
    moved = exported_cells(held, rows, cases, key)
    country = dict(us)
    country["scenarioPredictions"] = dict(us["scenarioPredictions"])
    country["scenarioPredictions"][key[0]] = {
        **us["scenarioPredictions"][key[0]],
        key[1]: {**us["scenarioPredictions"][key[0]][key[1]], **moved},
    }
    changed = sorted(m for m in held if json.dumps(moved[m]) != json.dumps(held[m]))
    return {"countries": {"us": country}}, moved, changed


def scope_check(scoped: dict, live: dict, reopened=frozenset(), decided=frozenset()):
    incumbents = {row["model"] for row in live["countries"]["us"]["modelStats"]}
    return driver.base_restoration_problems(
        scoped, live, incumbents, frozenset(reopened), decided=decided, limit=100
    )


def problems_on(key: tuple[str, str], models) -> list[str]:
    scenario, variable = key
    return [f"scenarioPredictions {scenario} {variable} {m} changed" for m in models]


def test_the_committed_spec_rules_exactly_the_ruled_case():
    """Review r3, Q2: on the committed spec, only what holds whether or not
    the lead records a permitted triage decision there during the release:
    its one ruled record."""
    records = driver.spec_records(driver.load_spec())
    assert [driver.spec_key(record) for record in records] == [RULED]


def test_the_release_decides_exactly_the_ruled_case(filled):
    """decided_cases on a spec that lists no triage decision (the filled
    MOCK spec): its one ruled record and nothing else. A spec with one is
    the next test's."""
    assert filled["triage_adjudications"] == []
    assert driver.triage_items() == []
    assert driver.decided_cases() == frozenset({RULED_CASE})


def test_decided_cases_names_the_ruled_records_and_the_triage_items():
    """With a MOCK triage decision in the spec, decided_cases names its case
    beside the ruled one."""
    item = MOCK_TRIAGE_ITEM
    assert driver.decided_cases(triage_spec()) == frozenset(
        {RULED_CASE, f"us__{item['scenario_id']}__{item['variable']}"}
    )


def _moved_fields(moved: dict, held: dict, changed: list[str]) -> set[str]:
    return {
        field
        for model in changed
        for field in held[model]
        if moved[model][field] != held[model][field]
    }


def test_check_a_passes_the_ruled_decision_on_release_20261027s_own_cells(
    ruled, base_live
):
    """On release 20261027's data from git, from text shaped like the seed's
    (review r3, Q1), the d2180 entry moves nine incumbent cells of the ruled
    output as triage builds them with the case kept: eight wrong answers in
    their classes and case note, one parse failure in its case note. Only
    the class fields and caseAnnotation move, since triage carries the
    published row annotations. Check (a) passes them with the case decided
    and not re-opened, and with it re-opened; holding every case to the
    base, the rule before review r2's N1, refuses all nine. With the case
    re-opened, its rows keep the seed-shaped text, so each cell whose row
    annotation release 20261027's amendments reworded moves in annotation
    too, which only the re-opened rule passes."""
    entry = ruled.after[RULED_CASE]
    scoped, moved, changed = decided_on_the_base(base_live, entry)
    held = base_live["countries"]["us"]["scenarioPredictions"][RULED[0]][RULED[1]]
    assert len(changed) == 9
    reclassed = [
        m for m in changed if moved[m]["failureSource"] != held[m]["failureSource"]
    ]
    assert len(reclassed) == 8
    fields = _moved_fields(moved, held, changed)
    assert fields == release_20261006.CLASS_CELL_FIELDS | {"caseAnnotation"}
    decided = driver.decided_cases()
    assert scope_check(scoped, base_live, decided=decided) == []
    assert scope_check(scoped, base_live, reopened={RULED_CASE}) == []
    assert scope_check(scoped, base_live) == problems_on(RULED, changed)
    scoped, moved, changed = decided_on_the_base(base_live, entry, {RULED_CASE})
    assert len(changed) == 9
    assert _moved_fields(moved, held, changed) == fields | {"annotation"}
    reworded = [
        m for m in changed if moved[m].get("annotation") != held[m].get("annotation")
    ]
    assert reworded
    assert scope_check(scoped, base_live, decided=decided) == problems_on(
        RULED, reworded
    )
    assert scope_check(scoped, base_live, {RULED_CASE}, decided) == []


def _committed_frames() -> tuple:
    return tuple(
        pd.read_csv(
            io.BytesIO(base_blob(ANNOTATIONS_PATH / name)), keep_default_na=False
        )
        for name in ANNOTATION_CSVS
    )


def _text_frames(*frames) -> tuple:
    return tuple(driver.annotation_text_frame(frame) for frame in frames)


def test_the_seed_shaped_text_differs_from_release_20261027s_on_terras_cases():
    """The premise of Q1, measured on git: Terra's text amendments make the
    committed files differ from the seed-shaped text on 1,406 rows and 76
    case notes, all on 117 cases, the ruled case among them, and nowhere
    else; the base's committed CSVs read back as the files spell them."""
    seed = _seed_shaped()
    committed = _committed_frames()
    for frame, name in zip(committed, ANNOTATION_CSVS, strict=True):
        assert driver.annotation_csv_text(frame).encode() == base_blob(
            ANNOTATIONS_PATH / name
        )
    rows_moved = seed["row"].annotation != committed[0].annotation
    from policybench.adjudications import _strip_adjudication_sentence

    notes = [_strip_adjudication_sentence(n) for n in committed[1].case_annotation]
    notes_moved = seed["case"].case_annotation != pd.Series(notes)
    cases = {
        *(c for c, moved in zip(_case_ids(committed[0]), rows_moved) if moved),
        *(c for c, moved in zip(_case_ids(committed[1]), notes_moved) if moved),
    }
    assert (int(rows_moved.sum()), int(notes_moved.sum()), len(cases)) == (
        1406,
        76,
        117,
    )
    assert RULED_CASE in cases
    assert cases == {
        item["case_id"] for item in _terra_amendments() if item["field"] != "reasoning"
    }


@pytest.mark.parametrize("state", ["kept", "reopened"])
def test_kept_cases_carry_release_20261027s_wording_on_its_data_from_git(ruled, state):
    """Review r3, Q1, on release 20261027's data from git. From text shaped
    like the seed's, the driver's builder gives every case it keeps release
    20261027's committed rows and case note byte for byte, d2180's decision
    (the entry the adjudicate step builds, its judge fields from a MOCK
    verdict) applied beside the base's. With the ruled case kept, its rows
    and note are the committed ones with the decision applied; re-opened,
    they keep the stage's text with it. The kept-case gate passes both, and
    with only the base's decisions the kept build is both committed files
    exactly."""
    from policybench.adjudications import adjudication_sentence

    entry = ruled.after[RULED_CASE]
    rejudged = frozenset() if state == "kept" else frozenset({RULED_CASE})
    decisions = [*driver.base_adjudications(), entry]
    built = driver.annotation_frames(_seed_shaped(), rejudged, decisions, [])
    assert driver.kept_annotation_problems(*built, rejudged, decisions) == []
    committed = _text_frames(*_committed_frames())
    got = _text_frames(*built)
    for want, have in zip(committed, got, strict=True):
        outside = [c != RULED_CASE for c in _case_ids(want)]
        assert (
            have[[c != RULED_CASE for c in _case_ids(have)]]
            .reset_index(drop=True)
            .equals(want[outside].reset_index(drop=True))
        )
    seed_rows, seed_cases = _text_frames(
        _seed_shaped()["row"], _seed_shaped()["case"].rename(columns=PLURAL)
    )
    source_rows, source_notes = (
        committed if state == "kept" else (seed_rows, seed_cases)
    )
    assert _on(got[0], RULED_CASE).annotation.tolist() == (
        _on(source_rows, RULED_CASE).annotation.tolist()
    )
    (note,) = _on(got[1], RULED_CASE).case_annotation
    (source,) = _on(source_notes, RULED_CASE).case_annotation
    assert note == source.rstrip() + adjudication_sentence(entry)
    (classes,) = _on(got[1], RULED_CASE)[
        ["case_failure_sources", "case_failure_subtypes"]
    ].values.tolist()
    assert classes == [
        entry["adjudicated_failure_source"],
        entry["adjudicated_failure_subtype"],
    ]
    if state == "kept":
        base_only = driver.annotation_frames(
            _seed_shaped(), frozenset(), driver.base_adjudications(), []
        )
        for frame, name in zip(base_only, ANNOTATION_CSVS, strict=True):
            assert driver.annotation_csv_text(frame).encode() == base_blob(
                ANNOTATIONS_PATH / name
            )


SEED_AUDIT = (
    Path.home() / "reviews/policybench-gpt-6-1-terra/worktree-results/stage/audit"
)


@pytest.mark.skipif(
    not (SEED_AUDIT / "cases").is_dir(), reason="needs release 20261027's audit seed"
)
def test_kept_cases_carry_release_20261027s_wording_on_the_bound_seed():
    """(local) Review r3, Q1, on the seed itself, held to the committed digest:
    collect_audit's text is the seed-shaped text rebuilt from git, and with
    every case kept the driver's builder and release 20261027's 63 decisions
    rebuild both of that release's committed files byte for byte."""
    from policybench.audit import collect_audit

    driver.verify_seed(driver.seed_digest(SEED_AUDIT))
    collected = collect_audit(Path("us"), SEED_AUDIT)
    rebuilt = _seed_shaped()
    for frame, column in (("row", "annotation"), ("case", "case_annotation")):
        assert collected[frame][column].tolist() == rebuilt[frame][column].tolist()
    built = driver.annotation_frames(
        collected, frozenset(), driver.base_adjudications(), []
    )
    for frame, name in zip(built, ANNOTATION_CSVS, strict=True):
        assert driver.annotation_csv_text(frame).encode() == base_blob(
            ANNOTATIONS_PATH / name
        )
    assert (
        driver.kept_annotation_problems(
            *built, frozenset(), driver.base_adjudications()
        )
        == []
    )


def _undecided_case(base_record: dict) -> tuple[str, str]:
    """The first case, in order, with a case note and an incumbent's
    substantive row that neither release 20261027's record nor this
    release's spec decides."""
    from policybench.adjudications import NON_SUBSTANTIVE_SOURCES

    rows, cases = base_annotation_frames()
    decided = {driver.spec_key(entry) for entry in base_record["adjudications"]}
    noted = set(zip(cases.scenario_id, cases.variable, strict=True))
    substantive = rows[~rows.failure_source.isin(NON_SUBSTANTIVE_SOURCES)]
    keys = set(zip(substantive.scenario_id, substantive.variable, strict=True))
    return min(keys & noted - decided - {RULED})


def test_check_a_refuses_the_same_decision_on_a_case_the_release_does_not_decide(
    ruled, base_live
):
    """The d2180 entry moved to another case (MOCK), one no decision of
    either release names, moves that case's cells as it moved the ruled
    case's, and check (a) refuses every one of them while only the ruled
    case is decided: a decision exempts its own case."""
    key = _undecided_case(ruled.base)
    entry = {**ruled.after[RULED_CASE], "scenario_id": key[0], "variable": key[1]}
    scoped, _, changed = decided_on_the_base(base_live, entry)
    assert changed
    decided = driver.decided_cases()
    assert scope_check(scoped, base_live, decided=decided) == problems_on(key, changed)
    case = frozenset({f"us__{key[0]}__{key[1]}"})
    assert scope_check(scoped, base_live, decided=case) == []


@pytest.mark.parametrize(
    "field, value",
    [
        ("annotation", "MOCK: a row annotation no decision wrote."),
        ("referenceExplanation", "MOCK: a reference explanation."),
        ("prediction", 1.0e9),
    ],
)
def test_check_a_holds_a_decided_cases_row_annotation_and_reference(
    ruled, base_live, field, value
):
    """On the ruled case decided and not re-opened, a row annotation or a
    referenceExplanation that is not release 20261027's stops check (a);
    re-opened, either passes. A prediction stops it either way."""
    scoped, moved, changed = decided_on_the_base(base_live, ruled.after[RULED_CASE])
    moved[changed[0]][field] = value
    refused = problems_on(RULED, changed[:1])
    decided = driver.decided_cases()
    assert scope_check(scoped, base_live, decided=decided) == refused
    reopened = scope_check(scoped, base_live, reopened={RULED_CASE}, decided=decided)
    assert reopened == (refused if field == "prediction" else [])


# --- The inherited gates are Terra's (review r1, M2) --------------------------
#
# The build report lists these functions as kept from Terra's scripts, byte
# for byte or with only names changed. Terra's suites test those bodies on
# finish_terra, freeze_terra and date_terra_judge_verdicts; these tests hold
# the Fable 5.2 copies to them, so an edit to one fails here until it gets
# tests of its own. A later fix that changes one takes it off these lists and
# adds its tests, as M6 did for the freeze's finalize.

# driver-build/tools/ndiff.py's rename map, Terra's names to this release's,
# with two temporary-folder prefixes and two messages that name the base by
# its role. Applied in order to each line of Terra's source.
TERRA_RENAMES = (
    (
        "judge_previous is not 20261014's plus one item",
        "judge_previous is not the base's plus one item",
    ),
    ('"20261014\'s entry names"', '"the base entry names"'),
    ("export-stage-terra-", "export-stage-fable52-"),
    (".terra-judge-provenance-", ".fable52-judge-provenance-"),
    ("20261027", "@REL_B@"),
    ("20261014", "@BASE_B@"),
    ("bf845cbe", "875fe1f6"),
    ("@REL_B@", "20261110"),
    ("@BASE_B@", "20261027"),
    ("finish_terra", "finish_fable52"),
    ("freeze_terra", "freeze_fable52"),
    ("date_terra_judge_verdicts", "date_fable52_judge_verdicts"),
    ("docs/terra/", "docs/fable52/"),
    ("terra/run", "fable52/run"),
    ("gpt-6.1-terra", "claude-fable-5.2"),
    ("GPT-6.1 Terra", "Claude Fable 5.2"),
    ('"terra"', '"fable52"'),
)
SCRIPTS = REPO / "scripts"
# (Fable 5.2 script, Terra script, kept byte for byte, kept with names only).
INHERITED = (
    (
        "finish_fable52.py",
        "finish_terra.py",
        (
            "NewRun",
            "_record_amendments",
            "_reported_models",
            "_tally_phrase",
            "account_data",
            "amend_annotations",
            "amend_text",
            "annotation_csv_text",
            "case_id",
            "committed_input_pins",
            "digest",
            "discover_new_models",
            "engine_older",
            "exclusions_text",
            "grounding_lookup",
            "head_blob",
            "incumbent_drift",
            "judge",
            "judge_identity_problems",
            "judge_isolation_problems",
            "judge_provenance_record",
            "load_amendments",
            "load_combined_predictions",
            "outside_the_judge",
            "partial_scores",
            "payload_text",
            "pin_inputs",
            "prepare_cases",
            "prepare_inputs",
            "record_text",
            "rejudged_cases",
            "release_exclusions_sha256",
            "repository_input_hashes",
            "require",
            "require_combined_predictions",
            "require_release_stage",
            "resolved_model_id",
            "restore_run_row_text",
            "reworded_since_seed",
            "seed_digest",
            "seed_prompt_digests",
            "set_aside",
            "spec_key",
            "spec_records",
            "transcript_problems",
            "triage_entry",
            "validate_keys",
            "validate_stage_path",
            "validate_verdicts",
            "verify_call_provenance",
            "verify_engine_pins",
            "verify_input_pins",
            "verify_judge_provenance",
            "verify_new_model_inputs",
            "verify_parse_failure_flags",
            "verify_prepared_inputs",
            "verify_usage",
            "verify_verdict_inventory",
            "withhold_addresses",
            "write_json",
        ),
        (
            "base_adjudication_record",
            "base_adjudications",
            "base_commit_blob",
            "base_exclusion_record",
            "base_payload_from_commit",
            "input_pins_record",
            "live_pointer",
            "load_seed",
            "resolve_base",
            "resolve_live_base",
            "seed_digest_text",
            "verify_base_predictions",
            "verify_seed",
            "build_release_exclusions",
            "export_stage",
            "new_model_row_differences",
            "verify_record_form",
            "verify_reopened_by_predictions",
            "verify_restatements",
            "write_judge_provenance",
        ),
    ),
    (
        "freeze_fable52.py",
        "freeze_terra.py",
        (
            "amendments_text",
            "annotation_differences",
            "digest",
            "evidence_runs",
            "freeze_amendments",
            "judged_cases",
            "manifest_core_digest",
            "payload_differences",
            "read_json",
            "release_pointer",
            "repository_input_changes",
            "verify_freezer_destinations",
            "verify_judge_provenance",
            "verify_repository_inputs",
            "verify_verdicts",
            "write_json",
        ),
        (
            "base_prediction_rows",
            "base_serving_config",
            "merge_serving",
            "serving_problems",
            "verify_receipt",
            "committed_amendments",
            "verify_held_references",
        ),
    ),
    (
        "date_fable52_judge_verdicts.py",
        "date_terra_judge_verdicts.py",
        ("bound_verdict", "case_id", "committed_record", "judge_disagreements"),
        (),
    ),
)
BYTE_FOR_BYTE = [
    (ours, terra, name) for ours, terra, kept, _ in INHERITED for name in kept
]
NAMES_ONLY = [
    (ours, terra, name) for ours, terra, _, renamed in INHERITED for name in renamed
]


@functools.cache
def _top_level_sources(script: str) -> dict[str, list[str]]:
    """Each top-level function's and class's lines, decorators included."""
    text = (SCRIPTS / script).read_text()
    lines = text.splitlines()
    return {
        node.name: lines[node.lineno - 1 - len(node.decorator_list) : node.end_lineno]
        for node in ast.parse(text).body
        if isinstance(node, (ast.FunctionDef, ast.ClassDef))
    }


def _renamed(lines: list[str]) -> list[str]:
    out = []
    for line in lines:
        for old, new in TERRA_RENAMES:
            line = line.replace(old, new)
        out.append(line)
    return out


def _code(lines: list[str]) -> str:
    """The definition's syntax tree without its docstrings: what it runs."""
    tree = ast.parse("\n".join(lines))
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            node.body = body[1:] or [ast.Pass()]
    return ast.dump(tree)


def test_the_inherited_lists_hold_the_build_reports_counts():
    counts = [(len(kept), len(renamed)) for _, _, kept, renamed in INHERITED]
    # The report's 21 driver functions kept with names changed less
    # provenance_note, whose note this release rewords (tested below), and its
    # 8 freeze functions less finalize, which M6 changed; its 17 freeze
    # functions kept byte for byte less verify_annotation_amendments, which
    # review r3's Q1 changed (its own tests are in the freeze's suite).
    assert counts == [(60, 20), (16, 7), (4, 0)]
    assert len(set(BYTE_FOR_BYTE)) == len(BYTE_FOR_BYTE)
    assert len(set(NAMES_ONLY)) == len(NAMES_ONLY)


@pytest.mark.parametrize("ours, terra, name", BYTE_FOR_BYTE)
def test_a_function_kept_byte_for_byte_is_terras(ours, terra, name):
    mine, theirs = _top_level_sources(ours), _top_level_sources(terra)
    assert name in mine and name in theirs
    assert mine[name] == theirs[name]


@pytest.mark.parametrize("ours, terra, name", NAMES_ONLY)
def test_a_function_kept_with_names_only_runs_terras_code(ours, terra, name):
    """After the rename map, its code (docstrings aside) is Terra's."""
    mine, theirs = _top_level_sources(ours), _top_level_sources(terra)
    assert name in mine and name in theirs
    assert _code(mine[name]) == _code(_renamed(theirs[name]))


def test_the_comparison_sees_a_one_token_edit():
    """The differential tests fail on an edit as small as one comparison."""
    lines = list(_top_level_sources("finish_fable52.py")["verify_usage"])
    assert _code(lines) == _code(_renamed(lines))
    edited = [line.replace(">= 0", "> 0", 1) for line in lines]
    assert edited != lines
    assert _code(edited) != _code(lines)


# Review r2, N2: a gate runs on its body and on the module-level values its
# body reads. Each value an inherited definition reads, and each value such a
# value reads in turn, bound in either script, must after the rename map be
# Terra's, save eight whose assignment this release writes on purpose: the
# seven it sets by design, which the tests at the top of this file pin (the
# counts BASE_MODELS and NEW_EXCLUSIONS, the base commit, engine and payload
# hash, the seed digest and the reference pins), and, review r3's Q4,
# CSV_NAME, which it assigns as a literal where Terra unpacks it from
# BUILT_FILES (its value is Terra's, pinned below). Review r3, Q4: the walk
# also follows each read of another script's value through a module alias
# (ALIASES), as the freeze reads driver.CSV_NAME.
BY_DESIGN = frozenset(
    {
        "BASE_COMMIT",
        "BASE_ENGINE",
        "BASE_MODELS",
        "NEW_EXCLUSIONS",
        "BASE_SHA256",
        "SEED_DIGEST_SHA256",
        "BASE_REFERENCE_SHA256",
        "CSV_NAME",
    }
)
# The module aliases through which a script reads another's values, each as
# (Fable 5.2 script, Terra script); test_the_walks_aliases_are_the_scripts_
# imports holds them to the scripts' imports.
ALIASES = {
    "driver": ("finish_fable52.py", "finish_terra.py"),
    "dating": ("date_fable52_judge_verdicts.py", "date_terra_judge_verdicts.py"),
}


@functools.cache
def _aliases(script: str) -> dict[str, str]:
    """The module aliases ``script`` imports from scripts/, each to its file."""
    return {
        alias.asname: f"{alias.name}.py"
        for node in ast.parse((SCRIPTS / script).read_text()).body
        if isinstance(node, ast.Import)
        for alias in node.names
        if alias.asname and (SCRIPTS / f"{alias.name}.py").is_file()
    }


def _bound(target: ast.expr) -> list[str]:
    """The names an assignment target binds (none for an item or attribute)."""
    if isinstance(target, ast.Name):
        return [target.id]
    if isinstance(target, (ast.Tuple, ast.List)):
        return [name for item in target.elts for name in _bound(item)]
    if isinstance(target, ast.Starred):
        return _bound(target.value)
    return []


@functools.cache
def _module_values(script: str) -> dict[str, list[list[str]]]:
    """Each module-level assignment's lines, under each name it binds."""
    text = (SCRIPTS / script).read_text()
    lines = text.splitlines()
    values: dict[str, list[list[str]]] = {}
    for node in ast.parse(text).body:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        source = lines[node.lineno - 1 : node.end_lineno]
        for target in targets:
            for name in _bound(target):
                values.setdefault(name, []).append(source)
    return values


def _loads(lines: list[str], here: tuple[str, str]) -> set[tuple]:
    """What ``lines`` of the script pair ``here`` read: each bare name, under
    ``here``, and (review r3, Q4) each attribute read on a module alias the
    script imports, under that alias's pair (ALIASES)."""
    aliases = _aliases(here[0])
    found = set()
    for node in ast.walk(ast.parse("\n".join(lines))):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            found.add((here, node.id))
        elif (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        ):
            found.add((ALIASES[node.value.id], node.attr))
    return found


@functools.cache
def _read_values(ours: str, terra: str) -> frozenset[tuple[str, str, str]]:
    """The module-level values the listed definitions of ``ours`` read, and
    the values those values read in turn, each as (script, Terra script,
    name) and bound in either script of its pair: through the module
    aliases too (review r3, Q4)."""
    kept, renamed = next(
        (kept, renamed) for mine, _, kept, renamed in INHERITED if mine == ours
    )
    sources = _top_level_sources(ours)
    pending = set().union(
        *(_loads(sources[name], (ours, terra)) for name in (*kept, *renamed))
    )
    seen: set[tuple] = set()
    while pending:
        pair, name = pending.pop()
        mine, theirs = _module_values(pair[0]), _module_values(pair[1])
        if (pair, name) in seen or (name not in mine and name not in theirs):
            continue
        seen.add((pair, name))
        for block in mine.get(name, []):
            pending |= _loads(block, pair)
    return frozenset((*pair, name) for pair, name in seen)


@functools.cache
def _walked() -> frozenset[tuple[str, str, str]]:
    """Every value an inherited definition of any script reads (_read_values)."""
    return frozenset().union(
        *(_read_values(ours, terra) for ours, terra, _, _ in INHERITED)
    )


def _same_value(ours: str, terra: str, name: str) -> bool:
    mine, theirs = _module_values(ours).get(name), _module_values(terra).get(name)
    return (
        mine is not None
        and theirs is not None
        and [_code(block) for block in mine]
        == [_code(_renamed(block)) for block in theirs]
    )


INHERITED_VALUES = sorted(value for value in _walked() if value[2] not in BY_DESIGN)


def test_the_walks_aliases_are_the_scripts_imports():
    """Review r3, Q4: each module alias a script imports names the script
    ALIASES gives it, on both sides of each pair."""
    for ours, terra, _, _ in INHERITED:
        for script, side in ((ours, 0), (terra, 1)):
            for alias, target in _aliases(script).items():
                assert ALIASES[alias][side] == target, (script, alias)
    assert {ours: _aliases(ours) for ours, _, _, _ in INHERITED} == {
        "finish_fable52.py": {},
        "freeze_fable52.py": {
            "dating": "date_fable52_judge_verdicts.py",
            "driver": "finish_fable52.py",
        },
        "date_fable52_judge_verdicts.py": {"driver": "finish_fable52.py"},
    }


def test_the_values_the_inherited_gates_read_include_the_reviews_sets():
    """Review r2's audit: 53 names in the driver (its 54 counted the
    os.environ item, which binds none), 11 in the freeze, none in the dating
    step; the 14 policy sets and patterns no fable52 test named among them.
    Review r3, Q4: through the module aliases, the freeze's definitions also
    read 16 of the driver's values and the dating step's 4, among them the
    two review r3 found in no walk, BASE_REPOSITORY_INPUT_FILES and
    CSV_NAME."""
    counts = {
        ours: dict(Counter(script for script, _, _ in _read_values(ours, terra)))
        for ours, terra, _, _ in INHERITED
    }
    assert counts == {
        "finish_fable52.py": {"finish_fable52.py": 53},
        "freeze_fable52.py": {"freeze_fable52.py": 11, "finish_fable52.py": 16},
        "date_fable52_judge_verdicts.py": {"finish_fable52.py": 4},
    }
    through = {
        name
        for script, _, name in _read_values("freeze_fable52.py", "freeze_terra.py")
        if script == "finish_fable52.py"
    }
    assert {"BASE_REPOSITORY_INPUT_FILES", "CSV_NAME"} <= through
    dating = _read_values(
        "date_fable52_judge_verdicts.py", "date_terra_judge_verdicts.py"
    )
    assert {name for _, _, name in dating} == {
        "ADJUDICATIONS",
        "ANNOTATIONS",
        "ROOT",
        "RUN_NAME",
    }
    names = {
        name for _, _, name in _read_values("finish_fable52.py", "finish_terra.py")
    }
    assert names >= {
        "JUDGE_ATTACHMENTS",
        "JUDGE_EVENT_TYPES",
        "ACCOUNT_KEY",
        "EMAIL_ADDRESS",
        "JUDGE_PROMPT_NUDGE",
        "JUDGE_SIDECAR_FIELDS",
        "JUDGE_PROVENANCE_KEYS",
        "JUDGE_PROVENANCE_ENTRY_KEYS",
        "WITHHELD_ADDRESS",
        "AMENDABLE_FIELDS",
        "TRIAGE_FIELDS",
        "TRIAGE_FINAL_SOURCES",
        "EXCLUSION_REASON_CODES",
        "PROVENANCE_GROUPS",
    }


def test_only_the_by_design_values_differ_from_terras():
    differ = {
        name
        for script, terra, name in _walked()
        if not _same_value(script, terra, name)
    }
    assert differ == BY_DESIGN


def test_csv_name_takes_terras_value_as_a_literal():
    """Review r3, Q4: CSV_NAME, which the freeze's verify_held_references
    reads through the driver alias, holds Terra's value; this release writes
    it as a literal where Terra unpacks it from BUILT_FILES, so BY_DESIGN
    lists it."""
    import finish_terra as terra

    assert driver.CSV_NAME == terra.CSV_NAME == "reference_outputs.csv"
    assert _module_values("finish_fable52.py")["CSV_NAME"] == [
        ['CSV_NAME = "reference_outputs.csv"']
    ]


@pytest.mark.parametrize("ours, terra, name", INHERITED_VALUES)
def test_a_value_an_inherited_gate_reads_is_terras(ours, terra, name):
    """After the rename map, its assignment's code is Terra's."""
    assert _same_value(ours, terra, name)


def test_the_value_comparison_sees_a_widened_set():
    """Review r2's case: "skill_listing" added to JUDGE_ATTACHMENTS."""
    (block,) = _module_values("finish_fable52.py")["JUDGE_ATTACHMENTS"]
    widened = [line.replace('"model",', '"model", "skill_listing",') for line in block]
    assert widened != block
    assert _code(widened) != _code(block)


# Review r3, Q4 (T P3-2): the comparison holds each walked value's
# assignment, so no other statement may change one. Each script's top-level
# statements are definitions, imports, its docstring, assignments to plain
# names and the lines TOP_LEVEL_EXTRAS lists; and no statement anywhere in it
# augments, stores into, deletes from or calls a mutating method on a walked
# value (bare, or through a module alias), sets an attribute of an aliased
# module, rebinds a walked name with ":=" or declares one global.
TOP_LEVEL_EXTRAS = {
    "finish_fable52.py": [
        'os.environ["OPENBLAS_NUM_THREADS"] = "1"',
        "sys.path.insert(0, str(ROOT))",
        'if __name__ == "__main__":\n    main()',
    ],
    "freeze_fable52.py": [
        'os.environ["OPENBLAS_NUM_THREADS"] = "1"',
        "sys.path.insert(0, str(ROOT))",
        'sys.path.insert(0, str(ROOT / "scripts"))',
        'if __name__ == "__main__":\n    main()',
    ],
    "date_fable52_judge_verdicts.py": [
        'sys.path.insert(0, str(ROOT / "scripts"))',
        'if __name__ == "__main__":\n    main()',
    ],
}
MUTATING_METHODS = frozenset(
    {
        "add",
        "append",
        "clear",
        "difference_update",
        "discard",
        "extend",
        "insert",
        "intersection_update",
        "pop",
        "popitem",
        "remove",
        "reverse",
        "setdefault",
        "sort",
        "symmetric_difference_update",
        "update",
        "__delitem__",
        "__iadd__",
        "__iand__",
        "__ior__",
        "__isub__",
        "__ixor__",
        "__setitem__",
    }
)


def _plain_target(target: ast.expr) -> bool:
    if isinstance(target, ast.Name):
        return True
    if isinstance(target, (ast.Tuple, ast.List)):
        return all(_plain_target(item) for item in target.elts)
    return isinstance(target, ast.Starred) and _plain_target(target.value)


def _top_level_extras(text: str) -> list[str]:
    """``text``'s top-level statements other than definitions, imports, the
    module docstring and assignments to plain names, as their source."""
    lines = text.splitlines()
    extras = []
    for index, node in enumerate(ast.parse(text).body):
        if isinstance(
            node, (ast.FunctionDef, ast.ClassDef, ast.Import, ast.ImportFrom)
        ):
            continue
        if (
            index == 0
            and isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            continue
        if isinstance(node, ast.Assign) and all(map(_plain_target, node.targets)):
            continue
        if isinstance(node, ast.AnnAssign) and _plain_target(node.target):
            continue
        extras.append("\n".join(lines[node.lineno - 1 : node.end_lineno]))
    return extras


def _walked_names(script: str) -> frozenset[str]:
    return frozenset(name for found, _, name in _walked() if found == script)


def _mutations(script: str, text: str) -> list[tuple[str, int]]:
    """Each statement in ``text``, ``script``'s source, that changes a
    walked value other than by a module-level assignment of its name: the
    node's type and line."""
    aliases, walked = _aliases(script), _walked_names(script)

    def aliased(node) -> bool:
        return (
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Name)
            and node.value.id in aliases
        )

    def base(node):
        while isinstance(node, (ast.Subscript, ast.Attribute)) and not aliased(node):
            node = node.value
        return node

    def is_walked(node) -> bool:
        if isinstance(node, ast.Name):
            return node.id in walked
        return aliased(node) and node.attr in _walked_names(aliases[node.value.id])

    def stores(target):
        if isinstance(target, (ast.Tuple, ast.List)):
            for item in target.elts:
                yield from stores(item)
        elif isinstance(target, ast.Starred):
            yield from stores(target.value)
        elif isinstance(target, (ast.Subscript, ast.Attribute)):
            yield target

    found = []
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, ast.AugAssign):
            hit = is_walked(base(node.target))
        elif isinstance(node, (ast.Assign, ast.Delete)):
            hit = any(is_walked(base(s)) for t in node.targets for s in stores(t))
        elif isinstance(node, ast.AnnAssign):
            hit = any(is_walked(base(s)) for s in stores(node.target))
        elif isinstance(node, ast.Call):
            func = node.func
            hit = (
                isinstance(func, ast.Attribute)
                and func.attr in MUTATING_METHODS
                and is_walked(base(func.value))
            ) or (
                isinstance(func, ast.Name)
                and func.id in ("setattr", "delattr")
                and bool(node.args)
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id in aliases
            )
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            hit = bool(set(node.names) & walked)
        elif isinstance(node, ast.NamedExpr):
            hit = is_walked(node.target)
        else:
            continue
        if hit:
            found.append((type(node).__name__, node.lineno))
    return found


@pytest.mark.parametrize("script", list(TOP_LEVEL_EXTRAS))
def test_a_scripts_top_level_holds_definitions_and_plain_values(script):
    assert (
        _top_level_extras((SCRIPTS / script).read_text()) == (TOP_LEVEL_EXTRAS[script])
    )


@pytest.mark.parametrize("script", list(TOP_LEVEL_EXTRAS))
def test_no_statement_changes_a_walked_value(script):
    assert _mutations(script, (SCRIPTS / script).read_text()) == []


# One MOCK snippet each, appended to a script's text: review r3's two cases
# and the other kinds of change the scan refuses. Each gives the statement
# that changes the value and whether the snippet is a top-level statement.
VALUE_CHANGES = {
    "a subscript store (review r3's case)": (
        "finish_fable52.py",
        'AMENDABLE_FIELDS["failure_source"] = "row annotation"',
        'AMENDABLE_FIELDS["failure_source"] = "row annotation"',
        "Assign",
        True,
    ),
    "an augmented assignment (review r3's case)": (
        "finish_fable52.py",
        'TRIAGE_FINAL_SOURCES -= {"llm_error"}',
        'TRIAGE_FINAL_SOURCES -= {"llm_error"}',
        "AugAssign",
        True,
    ),
    "a mutating call in a function": (
        "finish_fable52.py",
        'def widen():\n    EXCLUSION_REASON_CODES.update({"MOCK": "MOCK"})',
        'EXCLUSION_REASON_CODES.update({"MOCK": "MOCK"})',
        "Call",
        False,
    ),
    "a store through the driver alias": (
        "freeze_fable52.py",
        'driver.CSV_NAME = "other.csv"',
        'driver.CSV_NAME = "other.csv"',
        "Assign",
        True,
    ),
    "a mutating call through the driver alias": (
        "freeze_fable52.py",
        'driver.MODELS.update({"MOCK": "MOCK"})',
        'driver.MODELS.update({"MOCK": "MOCK"})',
        "Call",
        True,
    ),
    "a deletion through the driver alias": (
        "date_fable52_judge_verdicts.py",
        "def drop():\n    del driver.RUN_NAME",
        "del driver.RUN_NAME",
        "Delete",
        False,
    ),
    "a global rebinding": (
        "finish_fable52.py",
        "def rebind():\n    global AMENDABLE_FIELDS\n    AMENDABLE_FIELDS = {}",
        "global AMENDABLE_FIELDS",
        "Global",
        False,
    ),
    "setattr on the driver": (
        "freeze_fable52.py",
        'setattr(driver, "CSV_NAME", "other.csv")',
        'setattr(driver, "CSV_NAME", "other.csv")',
        "Call",
        True,
    ),
}


@pytest.mark.parametrize(
    "script, snippet, change, kind, top_level",
    list(VALUE_CHANGES.values()),
    ids=list(VALUE_CHANGES),
)
def test_the_scan_refuses_each_change_to_a_walked_value(
    script, snippet, change, kind, top_level
):
    """Each MOCK change the value comparison alone would pass: the scan names
    its statement alone, and a top-level one is also a statement the
    top-level check refuses."""
    edited = f"{(SCRIPTS / script).read_text()}\n{snippet}\n"
    ((found, line),) = _mutations(script, edited)
    assert (found, edited.splitlines()[line - 1].strip()) == (kind, change)
    extras = _top_level_extras(edited)
    assert extras == [*TOP_LEVEL_EXTRAS[script], *([snippet] if top_level else [])]


# Review r2, N2: the transcript check's sets and patterns are the runner's
# (scripts/run_audit_claude.sh), and the provenance record's are Terra's
# driver's, as Terra's tests held Terra's copy.

RUNNER = REPO / "scripts" / "run_audit_claude.sh"


def _runner_line(prefix: str) -> str:
    return next(
        line for line in RUNNER.read_text().splitlines() if line.startswith(prefix)
    )


def test_the_runners_attachment_allowlist_is_the_gates():
    line = _runner_line("ATTACHMENTS=")
    assert set(line.split('"')[1].split(",")) == driver.JUDGE_ATTACHMENTS


def test_the_runners_event_types_are_the_gates():
    line = _runner_line("EVENT_TYPES=")
    assert set(line.split('"')[1].split(",")) == driver.JUDGE_EVENT_TYPES


def test_the_runners_account_patterns_are_the_gates():
    script = RUNNER.read_text()
    assert driver.ACCOUNT_KEY.flags & re.IGNORECASE
    assert f'account_key = re.compile(r"{driver.ACCOUNT_KEY.pattern}", re.I)' in script
    assert f'email_address = re.compile(r"{driver.EMAIL_ADDRESS.pattern}")' in script


def test_the_runners_nudge_is_the_gates():
    assert _runner_line("PROMPT_NUDGE=") == (
        f'PROMPT_NUDGE="{driver.JUDGE_PROMPT_NUDGE}"'
    )


def test_the_transcript_and_provenance_values_are_terras_drivers():
    import finish_terra as terra

    for name in (
        "JUDGE_ATTACHMENTS",
        "JUDGE_EVENT_TYPES",
        "JUDGE_PROMPT_NUDGE",
        "JUDGE_PROVENANCE_KEYS",
        "JUDGE_PROVENANCE_ENTRY_KEYS",
        "JUDGE_SIDECAR_FIELDS",
        "WITHHELD_ADDRESS",
        "JUDGE_MODEL",
    ):
        assert getattr(driver, name) == getattr(terra, name), name
    for name in ("ACCOUNT_KEY", "EMAIL_ADDRESS"):
        ours, theirs = getattr(driver, name), getattr(terra, name)
        assert (ours.pattern, ours.flags) == (theirs.pattern, theirs.flags), name


# provenance_note rewords Terra's note: a case re-opens here only because
# Claude Fable 5.2 joined it. Terra's tests of the note, ported.


def test_the_provenance_note_gives_the_new_model_as_the_only_reason():
    note = driver.provenance_note([])
    assert note.startswith(
        "Provenance of the 0 new judge verdicts in the Claude Fable 5.2 stage: "
        "the cases it re-opened, each because Claude Fable 5.2 joined it. "
    )
    assert "reference build" not in note
    assert "Terra" not in note


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


# Export's gate sequence: every gate runs, and refuses, before build_payload.

EXPORT_GATES = (
    "require_combined_predictions",
    "verify_verdict_inventory",
    "stage_upgrade",
    "verify_reference_pins",
    "verify_staged_explanations",
    "verify_parse_failure_flags",
    "verify_new_model_inputs",
    "verify_judge_provenance",
    "verify_staged_annotations",
)


REAL_STAGED_EXPLANATIONS = driver.verify_staged_explanations


class _Built(Exception):
    """build_payload ran; the spy stops export there."""


@pytest.fixture
def export_spy(monkeypatch):
    calls = []
    for name in EXPORT_GATES:
        monkeypatch.setattr(
            driver,
            name,
            lambda *args, _name=name, **kw: calls.append((_name, args)),
        )
    monkeypatch.setattr(driver, "release_exclusions_sha256", lambda: "MOCK sha")
    monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": driver.BASE_TAG})
    monkeypatch.setattr(driver, "rejudged_cases", lambda stage: frozenset({"MOCK"}))
    monkeypatch.setattr(
        driver, "decided_cases", lambda spec=None: frozenset({"MOCK decided"})
    )

    def build(*args, **kw):
        calls.append(("build_payload", args))
        raise _Built

    monkeypatch.setattr(driver, "build_payload", build)
    return SimpleNamespace(calls=calls, monkeypatch=monkeypatch)


def _export(tmp_path, *, early=False, partial=False):
    args = SimpleNamespace(stage_dir=tmp_path / "stage", early=early, partial=partial)
    with pytest.raises(_Built):
        driver.export(args, tmp_path / "bundle", {"MOCK": "live payload"})
    return args


@pytest.mark.parametrize("tag", [driver.BASE_TAG, driver.RELEASE_TAG])
def test_export_runs_every_gate_before_it_builds_the_payload(export_spy, tmp_path, tag):
    export_spy.monkeypatch.setattr(driver, "live_pointer", lambda: {"tag": tag})
    args = _export(tmp_path)
    assert [name for name, _ in export_spy.calls] == [
        "require_combined_predictions",
        "verify_verdict_inventory",
        "stage_upgrade",
        "verify_reference_pins",
        "verify_reference_pins",
        "verify_staged_explanations",
        "verify_parse_failure_flags",
        "verify_new_model_inputs",
        "verify_judge_provenance",
        "verify_staged_annotations",
        "build_payload",
    ]
    calls = dict(enumerate(export_spy.calls))
    # Review r2, N8 (T P3-1): the first gate's argument too, the bundle.
    assert calls[0][1] == (tmp_path / "bundle",)
    assert calls[1][1] == (args.stage_dir / "audit",)
    assert calls[2][1] == (args.stage_dir,)
    frozen = "MOCK sha" if tag == driver.RELEASE_TAG else None
    assert calls[3][1] == (driver.SNAPSHOT, "committed reference", frozen)
    assert calls[4][1] == (tmp_path / "bundle" / "us", "staged reference", "MOCK sha")
    assert calls[5][1] == (tmp_path / "bundle",)
    assert calls[6][1] == calls[7][1] == (args.stage_dir,)
    assert calls[8][1] == (
        args.stage_dir / "audit" / "cases",
        frozenset({"MOCK"}),
        driver.JUDGE_PROVENANCE,
    )
    # Review r3, Q3: the bundle and the cases the stage re-opened.
    assert calls[9][1] == (tmp_path / "bundle", frozenset({"MOCK"}))


@pytest.mark.parametrize(
    "mode, skipped",
    [
        # An early rehearsal has no verdicts yet: it skips the judge gates.
        # Neither rehearsal holds triage's annotation files (review r3, Q3).
        (
            {"early": True},
            {
                "verify_verdict_inventory",
                "verify_parse_failure_flags",
                "verify_new_model_inputs",
                "verify_judge_provenance",
                "verify_staged_annotations",
            },
        ),
        # A partial export previews the common cohort: it skips the stage
        # binding and the reference pins.
        (
            {"partial": True},
            {"stage_upgrade", "verify_reference_pins", "verify_staged_annotations"},
        ),
    ],
)
def test_a_rehearsal_skips_only_its_named_gates(export_spy, tmp_path, mode, skipped):
    _export(tmp_path, **mode)
    names = [name for name, _ in export_spy.calls]
    assert names[-1] == "build_payload"
    assert set(EXPORT_GATES) - set(names) == skipped


@pytest.mark.parametrize("defect", ["edited", "missing"])
@pytest.mark.parametrize("mode", [{}, {"early": True}, {"partial": True}])
def test_export_refuses_explanations_off_the_base_before_it_builds(
    export_spy, tmp_path, defect, mode
):
    """Review r1, M7: the real gate, in every export mode, on the bundle's
    explanations: release 20261027's bytes pass to build_payload; one byte
    more, or none, stops export before it builds or writes."""
    export_spy.monkeypatch.setattr(
        driver, "verify_staged_explanations", REAL_STAGED_EXPLANATIONS
    )
    path = tmp_path / "bundle" / "annotations" / EXPLANATIONS_PATH.name
    path.parent.mkdir(parents=True)
    path.write_bytes(base_blob(EXPLANATIONS_PATH))
    _export(tmp_path, **mode)
    if defect == "edited":
        path.write_bytes(path.read_bytes() + b"\n")
    else:
        path.unlink()
    export_spy.calls.clear()
    args = SimpleNamespace(stage_dir=tmp_path / "stage", early=False, partial=False)
    args.__dict__.update(mode)
    with pytest.raises(SystemExit, match="rewords no reference explanation"):
        driver.export(args, tmp_path / "bundle", {})
    assert "build_payload" not in [name for name, _ in export_spy.calls]


# Review r1, M8: export's two reference-pin checks, real, at their call site
# (verify_reference_pins alone is tested above): the committed snapshot,
# whose exclusion record follows the live pointer (the base's until the
# freeze points it at this release), and the bundle, which scores on the
# release's record.

REAL_REFERENCE_PINS = driver.verify_reference_pins
REAL_RELEASE_EXCLUSIONS_SHA256 = driver.release_exclusions_sha256


def _pinned_export(export_spy, tmp_path, tag) -> tuple[Path, Path]:
    """The real pin checks; a committed snapshot and a bundle holding their
    pinned bytes; the live pointer at ``tag``. The record's digest is the
    real function's value (base_exclusion_record reads git at the committed
    snapshot's path, which this test moves)."""
    assert REAL_RELEASE_EXCLUSIONS_SHA256() == RELEASE_EXCLUSIONS_SHA256
    mp = export_spy.monkeypatch
    mp.setattr(driver, "verify_reference_pins", REAL_REFERENCE_PINS)
    mp.setattr(driver, "release_exclusions_sha256", lambda: RELEASE_EXCLUSIONS_SHA256)
    mp.setattr(driver, "live_pointer", lambda: {"tag": tag})
    snapshot = base_references(tmp_path / "snapshot")
    if tag == driver.RELEASE_TAG:
        (snapshot / EXCLUSIONS_NAME).write_text(release_text())
    mp.setattr(driver, "SNAPSHOT", snapshot)
    us = base_references(tmp_path / "bundle" / "us")
    (us / EXCLUSIONS_NAME).write_text(release_text())
    return snapshot, us


def _refused_before_build(export_spy, tmp_path, message) -> None:
    export_spy.calls.clear()
    args = SimpleNamespace(stage_dir=tmp_path / "stage", early=False, partial=False)
    with pytest.raises(SystemExit, match=message):
        driver.export(args, tmp_path / "bundle", {})
    assert "build_payload" not in [name for name, _ in export_spy.calls]


@pytest.mark.parametrize("tag", [driver.BASE_TAG, driver.RELEASE_TAG])
def test_export_passes_pinned_references_to_build_payload(export_spy, tmp_path, tag):
    _pinned_export(export_spy, tmp_path, tag)
    _export(tmp_path)
    assert export_spy.calls[-1][0] == "build_payload"


@pytest.mark.parametrize("name", [*driver.REFERENCE_FILES, "base record"])
def test_export_refuses_a_bundle_reference_off_its_pin_before_it_builds(
    export_spy, tmp_path, name
):
    """Each of the bundle's five reference files one byte off its pin, or the
    bundle scoring on release 20261027's record in place of the release's."""
    _, us = _pinned_export(export_spy, tmp_path, driver.BASE_TAG)
    if name == "base record":
        name = EXCLUSIONS_NAME
        (us / name).write_bytes(base_blob(SNAPSHOT_PATH / name))
    else:
        (us / name).write_bytes((us / name).read_bytes() + b"\n")
    _refused_before_build(
        export_spy, tmp_path, f"staged reference {re.escape(name)} does not match"
    )


@pytest.mark.parametrize("tag", [driver.BASE_TAG, driver.RELEASE_TAG])
@pytest.mark.parametrize("name", [*driver.REFERENCE_FILES, "other record"])
def test_export_refuses_a_committed_reference_off_its_pin_before_it_builds(
    export_spy, tmp_path, tag, name
):
    """Each committed reference file one byte off its pin, with the live
    pointer at the base (before the freeze) and at this release (after it),
    or the committed record that pointer does not name: the release's
    before the freeze, the base's after it."""
    snapshot, _ = _pinned_export(export_spy, tmp_path, tag)
    if name == "other record":
        name = EXCLUSIONS_NAME
        other = (
            release_text().encode()
            if tag == driver.BASE_TAG
            else base_blob(SNAPSHOT_PATH / name)
        )
        (snapshot / name).write_bytes(other)
    else:
        (snapshot / name).write_bytes((snapshot / name).read_bytes() + b"\n")
    _refused_before_build(
        export_spy, tmp_path, f"committed reference {re.escape(name)} does not match"
    )


@pytest.mark.parametrize("name", driver.REFERENCE_FILES)
def test_prepare_refuses_a_committed_reference_before_it_reads_the_pointer(
    workspace, monkeypatch, tmp_path, name
):
    """resolve_base holds the committed snapshot to its pins before it reads
    the live pointer (and before prepare stages anything)."""
    snapshot = base_references(tmp_path / "snapshot")
    (snapshot / name).write_bytes((snapshot / name).read_bytes() + b"\n")
    monkeypatch.setattr(driver, "SNAPSHOT", snapshot)
    monkeypatch.setattr(driver, "discover_new_models", lambda root: [])
    monkeypatch.setattr(driver, "live_pointer", lambda: pytest.fail("pointer read"))
    monkeypatch.setattr(
        driver, "prepare_inputs", lambda *a: pytest.fail("prepare_inputs ran")
    )
    with pytest.raises(
        SystemExit, match=f"committed reference {re.escape(name)} does not match"
    ):
        driver.main(
            ["--stage-dir", str(workspace.stage), "--step", "prepare"]
            + ["--runs-root", str(workspace.root / "runs")]
        )
    assert not workspace.stage.exists()


def test_prepare_reads_the_pointer_once_the_committed_references_pass(
    workspace, monkeypatch, tmp_path
):
    monkeypatch.setattr(driver, "SNAPSHOT", base_references(tmp_path / "snapshot"))
    monkeypatch.setattr(driver, "discover_new_models", lambda root: [])

    def pointer():
        raise SystemExit("MOCK: the pointer was read")

    monkeypatch.setattr(driver, "live_pointer", pointer)
    with pytest.raises(SystemExit, match="MOCK: the pointer was read"):
        driver.main(
            ["--stage-dir", str(workspace.stage), "--step", "prepare"]
            + ["--runs-root", str(workspace.root / "runs")]
        )


@pytest.mark.parametrize(
    "mode, reopened, decided",
    [
        ({}, frozenset({"MOCK"}), frozenset({"MOCK decided"})),
        ({"early": True}, frozenset(), frozenset()),
        ({"partial": True}, frozenset(), frozenset()),
    ],
    ids=["release", "early", "partial"],
)
def test_export_hands_the_scope_check_the_cases_it_reopened_and_decides(
    export_spy, tmp_path, mode, reopened, decided
):
    """Review r1, M9, and review r2, N1: a release export passes
    rejudged_cases' cases and decided_cases' cases, whose annotation fields
    check (a) lets differ from the base's. Review r3, Q5: a partial
    rehearsal runs no scope check, and an early one runs both on a stage
    nothing has judged or triaged, so neither passes any case."""
    seen = {}

    def build(*args, **kw):
        seen.update(kw)
        raise _Built

    export_spy.monkeypatch.setattr(driver, "build_payload", build)
    _export(tmp_path, **mode)
    assert seen["reopened"] == reopened
    assert seen["decided"] == decided


@pytest.mark.parametrize("gate", EXPORT_GATES)
def test_export_builds_nothing_once_a_gate_refuses(export_spy, tmp_path, gate):
    def refuse(*args, **kw):
        raise SystemExit(f"MOCK refusal by {gate}")

    export_spy.monkeypatch.setattr(driver, gate, refuse)
    args = SimpleNamespace(stage_dir=tmp_path / "stage", early=False, partial=False)
    with pytest.raises(SystemExit, match=f"MOCK refusal by {gate}"):
        driver.export(args, tmp_path / "bundle", {})
    assert "build_payload" not in [name for name, _ in export_spy.calls]
    assert not (tmp_path / "bundle").exists()
