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

import copy
import functools
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
from hypothesis import HealthCheck, assume, given, settings
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


RECORD_MUTATIONS = {
    "drop_a_base_record": lambda d: d["exclusions"].pop(0),
    "drop_the_ruled_record": lambda d: d["exclusions"].pop(-2),
    "edit_a_base_note": lambda d: d["exclusions"][3].update(note="edited"),
    "edit_the_ruled_value": lambda d: d["exclusions"][-2].update(
        alternative_value=1920.0
    ),
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
def test_a_record_that_differs_from_the_releases_is_refused_at_later_steps(
    pinned_directory, names
):
    doc = release_record()
    for name in names:
        RECORD_MUTATIONS[name](doc)
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


def _resumable(stage: Path, **receipt) -> None:
    stage.mkdir(parents=True, exist_ok=True)
    driver.write_json(
        stage / "stage.json", {"partial": False, "early": False, "files": {}, **receipt}
    )


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
    record = workspace.stage / BOUND
    record.parent.mkdir(parents=True)
    record.write_text(release_text())
    _resumable(
        workspace.stage,
        files={BOUND: RELEASE_EXCLUSIONS_SHA256},
        exclusions_installed={"sha256": RELEASE_EXCLUSIONS_SHA256},
    )
    record.write_text(release_text().replace("Certificate", "certificate", 1))
    with pytest.raises(SystemExit, match=f"staged input changed: {re.escape(BOUND)}"):
        driver.main(["--stage-dir", str(workspace.stage), "--step", step])
    assert calls == []


def _prepare_mocks(workspace, monkeypatch) -> dict:
    """discover_new_models, resolve_base, prepare_inputs and export mocked:
    prepare_inputs stages release 20261027's references (MOCK runs)."""
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
        st.floats(allow_nan=False, allow_infinity=False), min_size=1, max_size=20
    )
)
def test_incumbent_drift_keeps_serialized_types_and_key_order(rows):
    previous = {
        f"m{i}": {"model": f"m{i}", "exact": value, "n": 1935}
        for i, value in enumerate(rows)
    }
    stats = copy.deepcopy(list(previous.values()))
    assert driver.incumbent_drift(stats, previous) == []
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

    def run(answers, *, doc=None, base_answers=None):
        """The driver's payload and the base board's export."""
        base = export_board(
            write_board(
                root / "base", base_answers or answers, base_doc, MOCK_INCUMBENTS
            )
        )
        bundle = write_board(root / "release", answers, doc or release_doc)
        return driver.build_payload(bundle, base), base

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


@settings(max_examples=len(OPEN_ROWS), deadline=None)
@given(row=st.sampled_from(OPEN_ROWS))
def test_excluding_any_one_output_never_changes_another_outputs_hit(
    tmp_path_factory, row
):
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
    root = tmp_path_factory.getbasetemp() / "any-one-output"
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


# --- Preparation: the fold ------------------------------------------------------


@settings(max_examples=6, deadline=None)
@given(
    count=st.integers(1, 3),
    value=st.integers(-10000, 10000),
    extra=st.booleans(),
    record=st.sampled_from(["base", "release"]),
)
def test_the_fold_adds_exactly_1984_fable52_rows_on_the_reference_key_set(
    tmp_path_factory, count, value, extra, record
):
    import freeze_snapshot as freezer

    from policybench.fold_board import fold_board

    reference = pd.read_csv(io.BytesIO(base_blob(SNAPSHOT_PATH / CSV_NAME)))[driver.KEY]
    root = tmp_path_factory.mktemp("fable52-fold")
    frames = []
    for index in range(count + 1):
        frame = reference.copy()
        frame.insert(0, "model", NEW if index == count else f"incumbent-{index}")
        frame["prediction"] = float(value)
        frame["explanation"] = 'MOCK answer, with "quotes".'
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
        addition["provider_system_fingerprint"] = "fp_mock"
    addition_path = root / "fable52.csv"
    addition.to_csv(addition_path, index=False)
    scoring = base_references(root / "scoring")
    if record == "release":
        # The record decides what export scores, never what the fold keeps.
        (scoring / EXCLUSIONS_NAME).write_text(release_text())
    result = fold_board(
        base_path, [addition_path], scoring, root / "fold", export=False
    )
    assert result["models"] == count + 1 and result["excluded"] == {}
    folded = pd.read_csv(root / "fold/us/predictions.csv", low_memory=False)
    new_rows = folded[folded.model == NEW]
    assert len(new_rows) == 1984
    assert set(new_rows[driver.KEY].itertuples(index=False, name=None)) == set(
        reference.itertuples(index=False, name=None)
    )
    assert RULED in set(new_rows[driver.KEY].itertuples(index=False, name=None))
    assert set(addition.columns) <= set(new_rows.columns)
    for index in range(count):
        model = f"incumbent-{index}"
        assert freezer._model_prediction_rows_sha256(
            folded, model
        ) == freezer._model_prediction_rows_sha256(pd.read_csv(base_path), model)


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


@pytest.fixture
def adjudication_stage(stage, filled):
    """The base's adjudication record staged, and a MOCK judged case for the
    ruled output: a MOCK verdict that lists the new model among its MOCK
    wrong models, judged by Opus 5.5 on v2."""
    from policybench.judge_template import template_header

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
