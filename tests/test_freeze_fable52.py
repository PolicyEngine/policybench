"""Claude Fable 5.2's freeze keeps Terra's gates for a release that installs
no build: release 20261027's references, its 49 exclusions plus Max's d2180,
and 52 models.

MOCK DATA: every stage, receipt, payload stub and spec day below is
synthetic and lives in pytest's temporary directory. The committed
references, records, manifest and version list are only read, from git at
the base commit or from this checkout. The real freezer never writes, and
nothing calls an engine, provider or network service.
"""

from __future__ import annotations

import copy
import csv
import functools
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import date_fable52_judge_verdicts as dating  # noqa: E402
import finish_fable52 as driver  # noqa: E402
import freeze_fable52 as release  # noqa: E402
import freeze_snapshot as freezer  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
RUN = driver.RUN_NAME
FROZEN = Path("paper/snapshot/20260501/runs") / RUN
BOUND = f"publish/{RUN}/us/{release.EXCLUSIONS}"
NEW = "claude-fable-5.2"
RULED = ("scenario_122", "state_refundable_credits")
# MOCK days standing in for the lead's: the spec holds "[LEAD: ...]" for both.
SNAPSHOT_DATE = WRITTEN_ON = "2026-11-10"
REFERENCES = (
    "reference_outputs.csv",
    "reference_outputs.csv.meta.json",
    "scenarios.csv",
    "scenarios.csv.meta.json",
)


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


@pytest.fixture(autouse=True)
def no_real_freezer(monkeypatch):
    """A test reaching the actual snapshot writer fails before it writes."""

    def refuse():
        raise AssertionError("A test reached the real freeze_snapshot.main")

    monkeypatch.setattr(freezer, "main", refuse)


@pytest.fixture(autouse=True)
def cached_base_blobs(monkeypatch):
    """Every base read names one immutable commit: reuse its git bytes."""
    monkeypatch.setattr(driver, "base_commit_blob", base_blob)


# The committed spec's path, read once: the freeze harness below points
# driver.SPEC_PATH at a synthetic checkout's copy.
SPEC_PATH = driver.SPEC_PATH


def real_spec() -> dict:
    return json.loads((REPO / SPEC_PATH).read_text())


def filled_spec(**changes) -> dict:
    """The spec as the lead fills it before the freeze, with no triage
    decision: a test of the triage wave adds its own."""
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


BASE_RECORD = driver.base_exclusion_record()


def release_record() -> dict:
    return driver.build_release_exclusions(copy.deepcopy(BASE_RECORD), real_spec())


def release_text() -> str:
    return driver.exclusions_text(release_record())


# --- Constants and arguments --------------------------------------------------


def test_the_freeze_adds_fable52_to_the_base_board_under_the_driver_tag():
    assert release.NEW_MODELS == {"fable52": NEW}
    assert release.BOARD_MODELS == 52 == driver.BASE_MODELS + 1
    assert release.RELEASE_EXCLUSION_ENGINES == (
        "policyengine-us 1.755.4",
        "policyengine-us 2.15.17",
        "policyengine-us 2.38.6",
        "policyengine-us 2.60.0",
    )
    assert release.PINNED_REFERENCES == REFERENCES
    assert release.MANIFEST_PINNED == {
        *(("source_run_artifacts", RUN, "files", name) for name in REFERENCES),
        ("audit_annotation_artifacts", "files", release.EXPLANATIONS),
    }


@pytest.mark.parametrize(
    "argv, message",
    [
        (["--tag", "dashboard-data-latest"], "--tag must be dashboard-data-YYYYMMDD"),
        (["--tag", "dashboard-data-2026111"], "--tag must be dashboard-data-YYYYMMDD"),
        (["--dry-run", "--finalize"], "not allowed with argument"),
    ],
)
def test_main_refuses_a_bad_tag_or_both_modes(capsys, argv, message):
    with pytest.raises(SystemExit) as stopped:
        release.main(["--stage-dir", str(REPO / "results/local/stage"), *argv])
    assert stopped.value.code == 2
    assert message in capsys.readouterr().err


def test_main_refuses_a_stage_outside_the_checkout(capsys, tmp_path):
    with pytest.raises(SystemExit) as stopped:
        release.main(["--stage-dir", str(tmp_path / "stage")])
    assert stopped.value.code == 2
    assert "--stage-dir must be inside this checkout" in capsys.readouterr().err


def test_the_freezer_writes_into_this_checkout_only():
    release.verify_freezer_destinations(freezer)


@pytest.mark.parametrize(
    "name", ["ROOT", "SNAPSHOT_DIR", "RUN_DEST", "ANNOTATIONS_DEST"]
)
def test_a_freezer_writing_elsewhere_is_refused(monkeypatch, tmp_path, name):
    monkeypatch.setattr(freezer, name, tmp_path)
    with pytest.raises(SystemExit, match="would write outside this checkout"):
        release.verify_freezer_destinations(freezer)


def test_a_freezer_for_another_run_is_refused(monkeypatch):
    monkeypatch.setattr(freezer, "RUN_LABEL", "us_full_run_other")
    with pytest.raises(SystemExit, match="would write outside this checkout"):
        release.verify_freezer_destinations(freezer)


# --- The spec ----------------------------------------------------------------


@pytest.mark.parametrize(
    "snapshot",
    [
        "[LEAD: the UTC day of the freeze, YYYY-MM-DD]",
        "",
        None,
        "2026-11-1",
        "2026-13-01",
        "10 November 2026",
    ],
)
def test_a_spec_without_the_snapshot_day_stops_the_freeze(monkeypatch, snapshot):
    spec = filled_spec(snapshot_date=snapshot)
    monkeypatch.setattr(driver, "load_spec", lambda: spec)
    with pytest.raises(SystemExit, match="names no snapshot_date"):
        release.release_spec(driver.RELEASE_TAG)


@pytest.mark.parametrize(
    "written",
    [
        "[LEAD: the UTC day --step adjudicate-exclusions runs, YYYY-MM-DD]",
        "",
        None,
        "2026-11-1",
        "2026-13-01",
        "10 November 2026",
    ],
)
def test_a_spec_without_the_ruled_waves_written_day_stops_the_freeze(
    monkeypatch, written
):
    spec = filled_spec(adjudications_written_on=written)
    monkeypatch.setattr(driver, "load_spec", lambda: spec)
    with pytest.raises(SystemExit, match="names no adjudications_written_on"):
        release.release_spec(driver.RELEASE_TAG)


# A MOCK triage decision: the spec starts with none (review r1, M16: E F3).
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


@pytest.mark.parametrize(
    "written",
    [
        "[LEAD: the UTC day the triage decisions were written, YYYY-MM-DD]",
        "",
        None,
        "2026-11-1",
        "2026-13-01",
        "12 November 2026",
    ],
)
def test_a_spec_with_triage_decisions_and_no_triage_written_day_stops_the_freeze(
    monkeypatch, written
):
    """Before M16 the freeze read no triage day; the placeholder reached the
    record's date conventions."""
    spec = filled_spec(
        triage_adjudications=[dict(MOCK_TRIAGE_ITEM)],
        triage_decided_on=TRIAGE_DAY,
        triage_adjudications_written_on=written,
    )
    monkeypatch.setattr(driver, "load_spec", lambda: spec)
    with pytest.raises(SystemExit, match="names no triage_adjudications_written_on"):
        release.release_spec(driver.RELEASE_TAG)


def test_the_freeze_reads_the_triage_day_only_when_the_spec_lists_triage(
    monkeypatch,
):
    spec = filled_spec(triage_adjudications_written_on="[LEAD: day]")
    monkeypatch.setattr(driver, "load_spec", lambda: spec)
    assert release.release_spec(driver.RELEASE_TAG) == spec
    listed = filled_spec(
        triage_adjudications=[dict(MOCK_TRIAGE_ITEM)],
        triage_decided_on=TRIAGE_DAY,
        triage_adjudications_written_on=TRIAGE_DAY,
    )
    monkeypatch.setattr(driver, "load_spec", lambda: listed)
    assert release.release_spec(driver.RELEASE_TAG) == listed


@pytest.mark.parametrize(
    "field, value",
    [
        ("release_tag", "dashboard-data-20261111"),
        ("base_tag", "dashboard-data-20261014"),
        ("base_sha256", "0" * 64),
    ],
)
def test_a_spec_for_another_release_or_base_stops_the_freeze(monkeypatch, field, value):
    spec = filled_spec(**{field: value})
    monkeypatch.setattr(driver, "load_spec", lambda: spec)
    with pytest.raises(SystemExit, match="names another release or base"):
        release.release_spec(driver.RELEASE_TAG)


def test_a_filled_spec_is_the_freezes_for_its_own_tag_only(monkeypatch):
    spec = filled_spec()
    monkeypatch.setattr(driver, "load_spec", lambda: spec)
    assert release.release_spec(driver.RELEASE_TAG) == spec
    with pytest.raises(SystemExit, match="names another release or base"):
        release.release_spec("dashboard-data-20261111")


@settings(max_examples=80, deadline=None)
@given(day=st.one_of(st.dates().map(str), st.text(max_size=12)))
def test_only_a_real_day_fills_the_snapshot_date(day):
    spec = filled_spec(snapshot_date=day)
    with mock.patch.object(driver, "load_spec", lambda: spec):
        if driver.utc_day(day) is None:
            with pytest.raises(SystemExit, match="names no snapshot_date"):
                release.release_spec(driver.RELEASE_TAG)
        else:
            assert release.release_spec(driver.RELEASE_TAG)["snapshot_date"] == day


# --- The stage: no build, the release's record --------------------------------


def make_stage(root: Path) -> SimpleNamespace:
    """A MOCK release stage as --step install-exclusions leaves it: release
    20261027's references in scoring/ and the bundle, the release's record in
    both, and stage.json recording the install."""
    stage = root / "stage"
    text = release_text()
    for directory in (stage / "scoring", (stage / BOUND).parent):
        directory.mkdir(parents=True)
        for name in driver.REFERENCE_FILES:
            (directory / name).write_bytes(base_blob(FROZEN / name))
        (directory / release.EXCLUSIONS).write_text(text)
    digest = sha(text.encode())
    receipt = {
        "early": False,
        "partial": False,
        "files": {BOUND: digest},
        "exclusions_installed": {
            "base_sha256": driver.BASE_REFERENCE_SHA256[release.EXCLUSIONS],
            "sha256": digest,
            "spec_sha256": sha(REPO / driver.SPEC_PATH),
            "records": driver.RELEASE_EXCLUSIONS,
        },
    }
    (stage / "stage.json").write_text(json.dumps(receipt))
    return SimpleNamespace(path=stage, text=text, sha256=digest, receipt=receipt)


@pytest.fixture
def stage(tmp_path, monkeypatch):
    """make_stage's stage, with the engine and publication gates (tested in
    test_finish_fable52.py) recording each call."""
    made = make_stage(tmp_path)
    made.calls = []
    monkeypatch.setattr(
        driver, "verify_base_engine", lambda: made.calls.append("engine")
    )
    monkeypatch.setattr(
        driver, "verify_publication_record", lambda: made.calls.append("publication")
    )
    return made


def rewrite_receipt(stage, **changes) -> None:
    receipt = {**stage.receipt, **changes}
    for name, value in changes.items():
        if value is None:
            del receipt[name]
    (stage.path / "stage.json").write_text(json.dumps(receipt))


def test_the_record_is_release_20261027s_plus_the_ruled_record():
    assert release_record()["exclusions"][:-2] == BASE_RECORD["exclusions"][:-1]
    assert driver.spec_key(release_record()["exclusions"][-2]) == RULED
    assert sha(release_text().encode()) == driver.release_exclusions_sha256()


def test_the_freeze_takes_a_release_stage_with_no_build(stage):
    release.verify_no_upgrade(stage.path)
    assert stage.calls == ["engine", "publication"]


@pytest.mark.parametrize(
    "field, value", [("early", True), ("partial", True), ("partial", "false")]
)
def test_the_freeze_refuses_a_rehearsal_stage(stage, field, value):
    rewrite_receipt(stage, **{field: value})
    with pytest.raises(SystemExit, match="cannot become a release"):
        release.verify_no_upgrade(stage.path)
    assert stage.calls == []


@pytest.mark.parametrize("field", ["early", "partial"])
def test_the_freeze_refuses_a_stage_that_does_not_record_a_flag(stage, field):
    rewrite_receipt(stage, **{field: None})
    with pytest.raises(SystemExit, match="cannot become a release"):
        release.verify_no_upgrade(stage.path)


@pytest.mark.parametrize("marker", [*driver.INSTALL_MARKERS, "references_installed"])
def test_the_freeze_refuses_a_stage_that_records_a_build(stage, marker):
    if marker == "references_installed":
        rewrite_receipt(stage, references_installed={"engine": "2.60.0"})
    elif marker.endswith(".json"):
        (stage.path / marker).write_text("{}")
    else:
        (stage.path / marker).mkdir()
    with pytest.raises(SystemExit, match="records an installed reference build"):
        release.verify_no_upgrade(stage.path)
    assert stage.calls == []


def test_the_freeze_regates_the_audits_publication_record(stage, monkeypatch):
    def refuse():
        raise SystemExit("the audit's publication record disagrees")

    monkeypatch.setattr(driver, "verify_publication_record", refuse)
    with pytest.raises(SystemExit, match="publication record disagrees"):
        release.verify_no_upgrade(stage.path)
    assert stage.calls == ["engine"]


@pytest.mark.parametrize("name", [*REFERENCES, release.EXCLUSIONS])
def test_the_freeze_refuses_scoring_on_anything_but_the_pinned_files(stage, name):
    path = stage.path / "scoring" / name
    if name == release.EXCLUSIONS:
        # The base's own record, which the release no longer scores on.
        path.write_text(driver.exclusions_text(BASE_RECORD))
    else:
        path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(SystemExit, match="does not match its pin"):
        release.verify_no_upgrade(stage.path)


def test_the_installed_record_passes_as_install_wrote_it(stage):
    receipt = {"files": {BOUND: stage.sha256}}
    assert (
        release.verify_installed_exclusions(stage.path, receipt, stage.text)
        == stage.sha256
    )


INSTALLED_EDITS = {
    "the staged record's bytes": (
        lambda s: (s.path / BOUND).write_text(s.text + " "),
        "is not release 20261027's record plus the 1 ruled record",
    ),
    "a staged record missing": (
        lambda s: (s.path / BOUND).unlink(),
        "is not release 20261027's record plus the 1 ruled record",
    ),
    "the base's record staged": (
        lambda s: (s.path / BOUND).write_text(driver.exclusions_text(BASE_RECORD)),
        "is not release 20261027's record plus the 1 ruled record",
    ),
    "the installed hash": (
        lambda s: _installed(s, sha256="0" * 64),
        "does not record the release's 50 exclusions",
    ),
    "the base hash": (
        lambda s: _installed(s, base_sha256=s.sha256),
        "does not record the release's 50 exclusions",
    ),
    "a malformed spec hash": (
        lambda s: _installed(s, spec_sha256="[LEAD]"),
        "does not record the release's 50 exclusions",
    ),
    "the record count": (
        lambda s: _installed(s, records=49),
        "does not record the release's 50 exclusions",
    ),
    "the prepared file's hash": (
        lambda s: rewrite_receipt(s, files={BOUND: "0" * 64}),
        "does not record the release's 50 exclusions",
    ),
    "no install record": (
        lambda s: rewrite_receipt(s, exclusions_installed=None),
        "does not record the release's 50 exclusions",
    ),
}


def _installed(stage, **changes) -> None:
    rewrite_receipt(
        stage, exclusions_installed={**stage.receipt["exclusions_installed"], **changes}
    )


@pytest.mark.parametrize("edit", sorted(INSTALLED_EDITS))
def test_the_freeze_refuses_an_install_it_cannot_trace(stage, edit):
    change, message = INSTALLED_EDITS[edit]
    change(stage)
    with pytest.raises(SystemExit, match=message):
        release.verify_installed_exclusions(
            stage.path, {"files": {BOUND: stage.sha256}}, stage.text
        )


def test_the_receipt_must_bind_the_installed_record(stage):
    with pytest.raises(SystemExit, match="does not bind the installed"):
        release.verify_installed_exclusions(
            stage.path, {"files": {BOUND: "0" * 64}}, stage.text
        )


INSTALL_FIELDS = ("base_sha256", "sha256", "spec_sha256", "records")


@settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    fields=st.sets(
        st.sampled_from((*INSTALL_FIELDS, "references_installed", "engine", "note"))
    )
)
def test_only_the_install_steps_exact_fields_pass(tmp_path_factory, fields):
    made = make_stage(tmp_path_factory.mktemp("install-fields"))
    values = {**made.receipt["exclusions_installed"], "engine": "2.60.0", "note": ""}
    values["references_installed"] = True
    rewrite_receipt(made, exclusions_installed={f: values[f] for f in fields})
    receipt = {"files": {BOUND: made.sha256}}
    if fields == set(INSTALL_FIELDS):
        release.verify_installed_exclusions(made.path, receipt, made.text)
    else:
        with pytest.raises(SystemExit, match="does not record the release's"):
            release.verify_installed_exclusions(made.path, receipt, made.text)


# --- The payload's scored set -----------------------------------------------


def country(exclusions: list[dict], n: int = driver.RELEASE_SCORED) -> dict:
    return {
        "referenceExclusions": [
            {"scenarioId": r["scenario_id"], "variable": r["variable"]}
            for r in exclusions
        ],
        "modelStats": [{"model": f"mock-model-{index}", "n": n} for index in range(51)]
        + [{"model": NEW, "n": n}],
    }


def test_the_payload_names_the_releases_50_exclusions_and_scores_1934():
    exclusions = release_record()["exclusions"]
    release.verify_scored_outputs(country(exclusions), exclusions)


def test_the_payload_must_name_the_ruled_output():
    exclusions = release_record()["exclusions"]
    with pytest.raises(SystemExit, match="are not the release's 50"):
        release.verify_scored_outputs(country(BASE_RECORD["exclusions"]), exclusions)


def test_the_bases_49_exclusions_are_not_the_release():
    exclusions = BASE_RECORD["exclusions"]
    with pytest.raises(SystemExit, match="lists 49 outputs; the release excludes 50"):
        release.verify_scored_outputs(country(exclusions), exclusions)


@pytest.mark.parametrize("n", [1933, 1935])
@pytest.mark.parametrize("model", [0, 50, 51])
def test_every_model_fable52_included_is_scored_on_1934_outputs(model, n):
    exclusions = release_record()["exclusions"]
    payload = country(exclusions)
    payload["modelStats"][model]["n"] = n
    with pytest.raises(SystemExit, match="must be scored on 1934 outputs"):
        release.verify_scored_outputs(payload, exclusions)


@settings(max_examples=60, deadline=None)
@given(order=st.permutations(range(50)))
def test_the_payload_lists_the_exclusions_in_the_records_order(order):
    exclusions = release_record()["exclusions"]
    payload = country([exclusions[index] for index in order])
    if list(order) == list(range(50)):
        release.verify_scored_outputs(payload, exclusions)
    else:
        with pytest.raises(SystemExit, match="their order"):
            release.verify_scored_outputs(payload, exclusions)


# --- The version list ----------------------------------------------------------


def base_versions() -> dict:
    return json.loads(base_blob(release.VERSIONS))


def live(versions: dict) -> dict:
    (row,) = [row for row in versions["versions"] if row["id"] == versions["default"]]
    return row


def test_the_live_version_counts_the_ruled_record_on_its_engine():
    exclusions = release_record()["exclusions"]
    before = base_versions()
    result = release.release_versions(before, exclusions, SNAPSHOT_DATE)
    description = live(result)["description"]
    assert description == live(before)["description"].replace(
        "(the 49 excluded outputs keep the values they were decided on: 29 from "
        "policyengine-us 1.755.4, 18 from 2.15.17, 2 from 2.38.6, and the 16",
        "(the 50 excluded outputs keep the values they were decided on: 29 from "
        "policyengine-us 1.755.4, 18 from 2.15.17, 2 from 2.38.6, 1 from 2.60.0, "
        "and the 16",
    ).replace(" - 51 models", " - 52 models")
    assert description != live(before)["description"]
    assert live(result)["snapshotLabel"] == f"Snapshot {SNAPSHOT_DATE}"
    # Nothing else in the list moves, and a second pass changes nothing.
    rest = copy.deepcopy(result)
    live(rest).update(
        description=live(before)["description"],
        snapshotLabel=live(before)["snapshotLabel"],
    )
    assert rest == before
    assert release.release_versions(result, exclusions, SNAPSHOT_DATE) == result


def test_with_the_bases_records_the_count_keeps_the_bases_words():
    text = live(base_versions())["description"]
    assert release.count_exclusions(text, BASE_RECORD["exclusions"]) == text


@pytest.mark.parametrize("records", ["base", "unknown engine"])
def test_the_live_version_refuses_records_that_are_not_the_releases(records):
    exclusions = copy.deepcopy(release_record()["exclusions"])
    if records == "base":
        exclusions = BASE_RECORD["exclusions"]
    else:
        exclusions[0]["engine_version"] = "policyengine-us 2.78.0"
    with pytest.raises(SystemExit, match="counts exclusions decided on"):
        release.release_versions(base_versions(), exclusions, SNAPSHOT_DATE)


NEITHER = "neither release 20261027's nor this release's"


def test_a_reworded_description_stops_the_count():
    versions = base_versions()
    reworded = live(versions)["description"].replace(
        "keep the values they were decided on", "keep their decided values"
    )
    live(versions)["description"] = reworded
    with pytest.raises(SystemExit, match=NEITHER):
        release.release_versions(
            versions, release_record()["exclusions"], SNAPSHOT_DATE
        )
    with pytest.raises(SystemExit, match="changed form"):
        release.count_exclusions(reworded, release_record()["exclusions"])


# Review r1, M12 (Z P3-1): the words of the live description are release
# 20261027's. The review's case: a claim inserted where every pattern of
# count_exclusions still matches once.
CLAIM = ("same household facts", "same household facts; checked on 2.90.0")


def release_form() -> dict:
    return release.release_versions(
        base_versions(), release_record()["exclusions"], SNAPSHOT_DATE
    )


@pytest.mark.parametrize("form", ["base", "release"])
def test_the_live_description_keeps_the_bases_words(form):
    versions = base_versions() if form == "base" else release_form()
    exclusions = release_record()["exclusions"]
    # Either text the working tree may hold gives the release's description.
    assert release.release_versions(versions, exclusions, SNAPSHOT_DATE) == (
        release_form()
    )
    assert CLAIM[0] in live(versions)["description"]
    live(versions)["description"] = live(versions)["description"].replace(*CLAIM)
    with pytest.raises(SystemExit, match=NEITHER):
        release.release_versions(versions, exclusions, SNAPSHOT_DATE)


def test_the_live_description_comes_from_the_base_commit(monkeypatch):
    """The text the freeze writes starts from git's copy at BASE_COMMIT: with
    a claim in that copy and the working tree's text matching it, the claim
    is what the freeze would publish, so the source is git's, not the
    working tree's."""
    claimed = base_versions()
    live(claimed)["description"] = live(claimed)["description"].replace(*CLAIM)
    real = driver.base_commit_blob

    def blob(path):
        if Path(path) == release.VERSIONS:
            return json.dumps(claimed).encode()
        return real(path)

    monkeypatch.setattr(driver, "base_commit_blob", blob)
    result = release.release_versions(
        copy.deepcopy(claimed), release_record()["exclusions"], SNAPSHOT_DATE
    )
    assert CLAIM[1] in live(result)["description"]
    with pytest.raises(SystemExit, match=NEITHER):
        release.release_versions(
            base_versions(), release_record()["exclusions"], SNAPSHOT_DATE
        )


@settings(max_examples=60, deadline=None)
@given(
    form=st.sampled_from(["base", "release"]),
    at=st.integers(min_value=0),
    added=st.text(min_size=1, max_size=12),
)
def test_any_text_added_to_the_live_description_is_refused(form, at, added):
    versions = base_versions() if form == "base" else release_form()
    text = live(versions)["description"]
    at %= len(text) + 1
    live(versions)["description"] = text[:at] + added + text[at:]
    with pytest.raises(SystemExit, match=NEITHER):
        release.release_versions(
            versions, release_record()["exclusions"], SNAPSHOT_DATE
        )


@settings(max_examples=60, deadline=None)
@given(counts=st.tuples(*(st.integers(1, 40) for _ in range(4))))
def test_the_description_counts_any_records_by_engine_and_is_idempotent(counts):
    exclusions = [
        {"engine_version": engine}
        for engine, count in zip(release.RELEASE_EXCLUSION_ENGINES, counts, strict=True)
        for _ in range(count)
    ]
    result = release.release_versions(base_versions(), exclusions, SNAPSHOT_DATE)
    a, b, c, d = counts
    assert (
        f"(the {sum(counts)} excluded outputs keep the values they were decided "
        f"on: {a} from policyengine-us 1.755.4, {b} from 2.15.17, {c} from 2.38.6, "
        f"{d} from 2.60.0, and the 16 that move on 2.60.0 were re-reviewed and "
        "stay excluded); same household facts"
    ) in live(result)["description"]
    assert release.release_versions(result, exclusions, SNAPSHOT_DATE) == result


# --- The manifest ----------------------------------------------------------------


def manifest_leaves(value, path=()):
    if isinstance(value, dict) and value:
        for key, item in value.items():
            yield from manifest_leaves(item, (*path, key))
    elif isinstance(value, list) and value:
        for index, item in enumerate(value):
            yield from manifest_leaves(item, (*path, index))
    else:
        yield path


def base_manifest() -> dict:
    return json.loads(base_blob(release.SNAPSHOT / "manifest.json"))


# The manifest pins this release keeps at release 20261027's, spelled out.
STATED_PINS = [
    *(("source_run_artifacts", RUN, "files", name) for name in REFERENCES),
    ("audit_annotation_artifacts", "files", "us_case_reference_explanations.csv"),
]
# The manifest paths this release may change, spelled out (review r1, M10;
# S P3-4). The property below reads these and STATED_PINS, never the
# release's own constants, so a widened MANIFEST_CHANGES fails it.
STATED_CHANGES = (
    ("audit_annotation_artifacts", "files"),
    ("audit_annotation_artifacts", "developer_adjudications"),
    ("audit_annotation_artifacts", "judge_provenance"),
    ("audit_annotation_artifacts", "note"),
    ("committed_snapshot_artifacts", "model_serving_config.json"),
    ("committed_snapshot_artifacts", "us_impact_summary_by_model.csv"),
    ("description",),
    ("files",),
    ("live_dashboard_artifact",),
    ("model_response_date",),
    ("published_dashboard_artifact",),
    ("reference_exclusions",),
    ("reference_output_refresh", "snapshot_date"),
    ("rendered_paper_artifacts",),
    ("reproducibility_notes",),
    ("scope", "models"),
    ("snapshot_date",),
    ("source_run_artifacts", RUN, "files"),
)


def test_the_release_may_change_exactly_the_stated_manifest_paths():
    assert release.MANIFEST_CHANGES == STATED_CHANGES
    assert release.MANIFEST_PINNED == set(STATED_PINS)


def set_leaf(manifest: dict, path: tuple, value) -> None:
    cursor = manifest
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = value


@pytest.mark.parametrize("path", STATED_PINS)
def test_the_manifest_keeps_every_stated_base_pin(path):
    after = base_manifest()
    set_leaf(after, path, "0" * 64)
    assert release.manifest_problems(base_manifest(), after) == [path]


@pytest.mark.parametrize(
    "path",
    [
        ("snapshot_date",),
        ("description",),
        ("scope", "models"),
        ("source_run_artifacts", RUN, "files", release.EXCLUSIONS),
        ("source_run_artifacts", RUN, "files", "predictions.csv.gz"),
    ],
)
def test_the_manifest_may_change_what_the_release_states(path):
    after = base_manifest()
    set_leaf(after, path, "changed")
    assert release.manifest_problems(base_manifest(), after) == []


@settings(max_examples=75, deadline=None)
@given(picks=st.sets(st.integers(min_value=0, max_value=10**6), max_size=6))
def test_the_manifest_may_change_only_where_the_release_says(picks):
    before = base_manifest()
    after = copy.deepcopy(before)
    leaves = tuple(manifest_leaves(before))
    changed = {leaves[pick % len(leaves)] for pick in picks}
    for path in changed:
        set_leaf(after, path, "changed")
    expected = {
        path
        for path in changed
        if path in STATED_PINS
        or not any(path[: len(prefix)] == prefix for prefix in STATED_CHANGES)
    }
    assert set(release.manifest_problems(before, after)) == expected


# --- References, explanations and held values ------------------------------------


@pytest.fixture
def frozen(tmp_path):
    """A MOCK stage bundle and committed snapshot, both release 20261027's
    references, with the release's record staged and the base's committed,
    as before the freeze."""
    source_us = tmp_path / "stage" / BOUND
    source_us = source_us.parent
    snapshot = tmp_path / "snapshot"
    frozen_run = snapshot / "runs" / RUN
    for directory in (source_us, frozen_run):
        directory.mkdir(parents=True)
        for name in driver.REFERENCE_FILES:
            (directory / name).write_bytes(base_blob(FROZEN / name))
    text = release_text()
    (source_us / release.EXCLUSIONS).write_text(text)
    (snapshot / "us_reference_outputs.csv").write_bytes(
        base_blob(release.SNAPSHOT / "us_reference_outputs.csv")
    )
    return SimpleNamespace(
        source_us=source_us,
        frozen_run=frozen_run,
        snapshot=snapshot,
        manifest=base_manifest(),
        text=text,
        sha256=sha(text.encode()),
    )


def check_references(frozen) -> None:
    release.verify_references(
        frozen.source_us, frozen.frozen_run, frozen.manifest, frozen.sha256
    )


def test_the_references_are_the_bases_before_and_after_the_freeze(frozen):
    check_references(frozen)
    (frozen.frozen_run / release.EXCLUSIONS).write_text(frozen.text)
    pins = frozen.manifest["source_run_artifacts"][RUN]["files"]
    pins[release.EXCLUSIONS] = frozen.sha256
    check_references(frozen)


REFERENCE_EDITS = {
    "a staged reference": (
        lambda f: _append(f.source_us / "reference_outputs.csv"),
        "Staged reference_outputs.csv changed: this release revises no reference",
    ),
    "a staged sidecar": (
        lambda f: _append(f.source_us / "scenarios.csv.meta.json"),
        "Staged scenarios.csv.meta.json changed",
    ),
    "the base's record staged": (
        lambda f: (f.source_us / release.EXCLUSIONS).write_text(
            driver.exclusions_text(BASE_RECORD)
        ),
        "Staged reference_exclusions.json changed: it is not the release's record",
    ),
    "a committed reference": (
        lambda f: _append(f.frozen_run / "scenarios.csv"),
        "Committed scenarios.csv changed: it is not release 20261027's",
    ),
    "a committed record of neither release": (
        lambda f: _append(f.frozen_run / release.EXCLUSIONS),
        "Committed reference_exclusions.json changed: it is neither",
    ),
    "a reference's manifest pin": (
        lambda f: _pin(f, "reference_outputs.csv.meta.json", "0" * 64),
        "Manifest pin for reference_outputs.csv.meta.json is not release 20261027's",
    ),
    "the record's manifest pin": (
        lambda f: _pin(f, release.EXCLUSIONS, "0" * 64),
        "Manifest pin for reference_exclusions.json is neither",
    ),
    "the committed us_reference_outputs.csv": (
        lambda f: _append(f.snapshot / "us_reference_outputs.csv"),
        "Committed us_reference_outputs.csv changed",
    ),
    "the us_reference_outputs.csv pin": (
        lambda f: f.manifest["committed_snapshot_artifacts"].update(
            {"us_reference_outputs.csv": "0" * 64}
        ),
        "Manifest pin for us_reference_outputs.csv is not release 20261027's",
    ),
    "the explanations pin": (
        lambda f: f.manifest["audit_annotation_artifacts"]["files"].update(
            {release.EXPLANATIONS: "0" * 64}
        ),
        "Manifest pin for us_case_reference_explanations.csv",
    ),
}


def _append(path: Path) -> None:
    path.write_bytes(path.read_bytes() + b"\n")


def _pin(frozen, name: str, value: str) -> None:
    frozen.manifest["source_run_artifacts"][RUN]["files"][name] = value


@pytest.mark.parametrize("edit", sorted(REFERENCE_EDITS))
def test_a_reference_off_the_bases_pins_is_refused(frozen, edit):
    change, message = REFERENCE_EDITS[edit]
    change(frozen)
    with pytest.raises(SystemExit, match=message):
        check_references(frozen)


def test_the_explanations_keep_the_bases_bytes(tmp_path):
    staged = tmp_path / "annotations"
    staged.mkdir()
    path = staged / release.EXPLANATIONS
    path.write_bytes(base_blob(release.ANNOTATIONS / release.EXPLANATIONS))
    release.verify_explanations(staged)
    _append(path)
    with pytest.raises(SystemExit, match="rewords no reference explanation"):
        release.verify_explanations(staged)
    path.unlink()
    with pytest.raises(SystemExit, match="rewords no reference explanation"):
        release.verify_explanations(staged)


def test_held_references_keep_their_decided_values(frozen):
    release.verify_held_references(frozen.source_us)
    held = json.loads(base_blob(Path("reference_audit/held_references.json")))
    key = driver.spec_key(held["records"][0])
    path = frozen.source_us / driver.CSV_NAME
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    for row in rows:
        if (row["scenario_id"], row["variable"]) == key:
            row["value"] = str(float(row["value"]) + 1.0)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(SystemExit, match="Held reference changed"):
        release.verify_held_references(frozen.source_us)


def test_the_staged_sidecar_passes_the_freezers_engine_setup_gates(tmp_path):
    (tmp_path / driver.META_NAME).write_bytes(base_blob(FROZEN / driver.META_NAME))
    previous = freezer.REFERENCE_META_SOURCE
    setup = release.reference_engine_setup(freezer, tmp_path)
    assert setup == {"convention_count": 9, "output_scope_adapter_count": 1}
    assert setup["convention_count"] in freezer.NUMBER_WORDS
    assert freezer.REFERENCE_META_SOURCE == previous


def test_a_sidecar_off_its_fix_module_pin_stops_the_preflight(tmp_path):
    meta = json.loads(base_blob(FROZEN / driver.META_NAME))
    meta["revisions"][-1]["fix_modules"][0]["sha256"] = "0" * 64
    (tmp_path / driver.META_NAME).write_text(json.dumps(meta))
    previous = freezer.REFERENCE_META_SOURCE
    with pytest.raises(SystemExit, match="pins sha256"):
        release.reference_engine_setup(freezer, tmp_path)
    assert freezer.REFERENCE_META_SOURCE == previous


def test_configure_freezer_reads_the_stage_and_keeps_the_committed_pins(tmp_path):
    fake = SimpleNamespace(
        REFERENCE_PINS={"reference_outputs.csv": "pinned by a build"},
        audit_judge_provenance=lambda **kwargs: kwargs,
        developer_adjudications_block=lambda **kwargs: kwargs,
        freeze_serving_configuration=lambda destination: None,
    )
    original = fake.freeze_serving_configuration
    pointer = {"tag": "t", "asset": "a", "url": "u", "sha256": "s", "bytes": 1}
    source_run = tmp_path / "run"
    release.configure_freezer(
        fake,
        snapshot_date=SNAPSHOT_DATE,
        source_run=source_run,
        payload_path=tmp_path / "data-board52.json",
        pointer={**pointer, "browser_download_url": "x"},
        evidence_paths={"run": "evidence"},
        cases_dir=tmp_path / "cases",
        judged_case_ids=("case-1",),
        previous_serving={},
        incumbents=set(),
        runs={},
    )
    assert fake.REFERENCE_PINS is None
    assert (fake.SNAPSHOT_DATE, fake.SOURCE_RUN) == (SNAPSHOT_DATE, source_run)
    assert fake.SOURCE_US == source_run / "us"
    assert fake.SOURCE_ANNOTATIONS == source_run / "annotations"
    assert fake.REFERENCE_META_SOURCE == source_run / "us" / driver.META_NAME
    assert fake.PUBLISHED_DASHBOARD_ARTIFACT == pointer
    assert fake.audit_judge_provenance() == {
        "cases_dir": tmp_path / "cases",
        "case_ids": ("case-1",),
    }
    assert fake.developer_adjudications_block() == {"cases_dir": tmp_path / "cases"}
    assert fake.freeze_serving_configuration is not original


# --- Gates the freeze runs again -------------------------------------------------


@pytest.mark.parametrize("pending", [[], ["case_007"]])
def test_the_freeze_runs_the_drivers_verdict_gate_on_the_bound_seed(
    tmp_path, monkeypatch, pending
):
    seen = {}
    monkeypatch.setattr(driver, "load_seed", lambda stage: ("seed of", stage))

    def validate(audit, **kwargs):
        seen.update(audit=audit, **kwargs)
        return pending

    monkeypatch.setattr(driver, "validate_verdicts", validate)
    if pending:
        with pytest.raises(SystemExit, match="1 staged verdicts fail validation"):
            release.verify_verdicts(tmp_path)
    else:
        release.verify_verdicts(tmp_path)
    # It changes nothing: no remove_invalid.
    assert seen == {"audit": tmp_path / "audit", "seed": ("seed of", tmp_path)}


def test_the_record_gate_hands_triage_the_specs_decisions(tmp_path, monkeypatch):
    import policybench.adjudications as adjudications

    items = ["MOCK triage item"]
    seen = {}
    monkeypatch.setattr(driver, "triage_items", lambda: items)
    monkeypatch.setattr(driver, "decision_wave", lambda triage: ("wave of", triage))
    monkeypatch.setattr(driver, "base_adjudication_record", lambda: "BASE TEXT")
    monkeypatch.setattr(
        driver,
        "verify_record_form",
        lambda text, base, wave: seen.update(form=(text, base, wave)),
    )
    monkeypatch.setattr(adjudications, "load_adjudications", lambda path: "AFTER")
    monkeypatch.setattr(driver, "base_adjudications", lambda: "BASE")

    def changes(base, after, rejudged, amendments, cases_dir, *, triage):
        seen["changes"] = (base, after, triage)
        raise SystemExit("stopped after the change gate")

    monkeypatch.setattr(driver, "verify_adjudication_changes", changes)
    staged = tmp_path / release.ADJUDICATIONS
    staged.write_text("STAGED")
    with pytest.raises(SystemExit, match="stopped after the change gate"):
        release.verify_adjudication_record(staged, tmp_path, frozenset(), [], tmp_path)
    assert seen == {
        "form": ("STAGED", "BASE TEXT", ("wave of", items)),
        "changes": ("BASE", "AFTER", items),
    }


TIMING = str(driver.REPOSITORY_INPUT_FILES[2])
# The driver's record gate itself: the finalize fixture replaces the module's.
PUBLICATION_GATE = driver.verify_publication_record


@pytest.fixture
def finalizing(tmp_path, monkeypatch):
    """A completed freeze's MOCK receipt; the repository's hashes and their
    changes come from the test, and driver.stage_upgrade and the publication
    record's currency check record their calls."""
    stage = tmp_path / "stage"
    stage.mkdir()
    (stage / "stage.json").write_text(json.dumps({"early": False, "partial": False}))
    required = {str(name): "0" * 64 for name in driver.REPOSITORY_INPUT_FILES}
    receipt = {
        "repository_inputs": {
            **required,
            "app/public/paper/policybench.pdf": None,
            "app/public/paper/web/": "directory",
        },
        "repository_postfreeze": {
            str(release.SNAPSHOT / "manifest.json"): "0" * 64,
            str(release.VERSIONS): "0" * 64,
        },
        "postfreeze_manifest_core": "0" * 64,
    }
    made = SimpleNamespace(
        stage=stage,
        receipt=receipt,
        calls=[],
        changed=[],
        publication=[],
        references=[],
    )
    # The committed snapshot holds release 20261027's record until a freeze:
    # the reference check records its call here (the H tests run it).
    monkeypatch.setattr(
        release,
        "verify_committed_references",
        lambda snapshot, sha256: made.references.append((snapshot, sha256)),
    )
    monkeypatch.setattr(driver, "stage_upgrade", made.calls.append)
    monkeypatch.setattr(
        driver,
        "verify_publication_record",
        lambda **kwargs: made.publication.append(kwargs),
    )
    monkeypatch.setattr(driver, "repository_input_hashes", lambda root: {})
    monkeypatch.setattr(
        release,
        "repository_input_changes",
        lambda receipt, current, accept_postrender: list(made.changed),
    )
    return made


def test_finalize_regates_a_rewritten_publication_record(finalizing):
    finalizing.changed.append(TIMING)
    # The MOCK receipt's manifest core stops it after the re-gate.
    with pytest.raises(SystemExit, match="Manifest core changed"):
        release.finalize(finalizing.stage, finalizing.receipt, freezer, SNAPSHOT_DATE)
    assert finalizing.calls == [finalizing.stage]
    assert finalizing.publication == [{"checked_on_or_after": SNAPSHOT_DATE}]


def test_finalize_refuses_without_a_new_publication_record(finalizing):
    """A check that did not run, or stopped before it wrote, leaves
    sweep_timing.json as export bound it: finalize stops before any gate."""
    with pytest.raises(SystemExit, match="unchanged since export"):
        release.finalize(finalizing.stage, finalizing.receipt, freezer, SNAPSHOT_DATE)
    assert finalizing.calls == [] and finalizing.publication == []


@pytest.mark.parametrize("day", [None, "", "[LEAD: the UTC day of the freeze]"])
def test_finalize_refuses_without_a_snapshot_day(finalizing, day):
    finalizing.changed.append(TIMING)
    with pytest.raises(SystemExit, match="Finalize needs the spec's snapshot_date"):
        release.finalize(finalizing.stage, finalizing.receipt, freezer, day)
    assert finalizing.calls == [] and finalizing.publication == []


def publication_root(root: Path) -> Path:
    """A synthetic checkout root holding release 20261027's publication record
    (the 2026-10-29 check of policyengine-us 2.78.0), its builder and the
    committed reference-build/, from git at the base commit."""
    timing = json.loads(base_blob(driver.REFERENCE_AUDIT / TIMING_RECORD))
    built = [n for n in timing["publication_check"]["build_sha256"] if n != "builder"]
    for relative in (
        driver.REFERENCE_AUDIT / TIMING_RECORD,
        driver.REFERENCE_AUDIT / "scripts/build_references_upgrade.py",
        *(driver.REFERENCE_BUILD_DIR / name for name in built),
    ):
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(base_blob(relative))
    return root


TIMING_RECORD = Path("verification/sweep_timing.json")


def test_finalize_stops_on_the_base_releases_publication_record(
    finalizing, monkeypatch, tmp_path
):
    """The 2026-10-29 record passes the record gate but read PyPI before the
    snapshot day, so finalize stops on it."""
    root = publication_root(tmp_path / "root")
    real = PUBLICATION_GATE
    finalizing.changed.append(TIMING)
    monkeypatch.setattr(
        driver, "verify_publication_record", lambda **kw: real(root, **kw)
    )
    real(root)
    with pytest.raises(SystemExit, match="does not check the newest"):
        release.finalize(finalizing.stage, finalizing.receipt, freezer, SNAPSHOT_DATE)
    assert finalizing.calls == [finalizing.stage]


def test_main_hands_finalize_the_specs_snapshot_day(monkeypatch, tmp_path):
    seen = {}
    stage = tmp_path / "stage"
    stage.mkdir()
    monkeypatch.setattr(release, "ROOT", tmp_path)
    monkeypatch.setattr(release, "verify_freezer_destinations", lambda freezer: None)
    monkeypatch.setattr(driver, "require_combined_predictions", lambda path: None)
    monkeypatch.setattr(release, "verify_receipt", lambda *args: {"MOCK": "receipt"})
    monkeypatch.setattr(driver, "load_spec", lambda: filled_spec())
    monkeypatch.setattr(
        release, "finalize", lambda *args: seen.setdefault("finalize", args)
    )
    release.main(["--stage-dir", str(stage), "--finalize"])
    assert seen["finalize"][0] == stage.resolve()
    assert seen["finalize"][1] == {"MOCK": "receipt"}
    assert seen["finalize"][3] == SNAPSHOT_DATE


def test_finalize_stops_on_a_publication_record_the_driver_refuses(
    finalizing, monkeypatch
):
    finalizing.changed.append(TIMING)

    def refuse(stage):
        raise SystemExit("the audit's publication record names an older engine")

    monkeypatch.setattr(driver, "stage_upgrade", refuse)
    with pytest.raises(SystemExit, match="names an older engine"):
        release.finalize(finalizing.stage, finalizing.receipt, freezer, SNAPSHOT_DATE)
    assert finalizing.publication == []


def test_finalize_refuses_a_change_outside_the_render(finalizing):
    finalizing.changed.extend([TIMING, "uv.lock"])
    with pytest.raises(SystemExit, match="Finalize refuses repository changes"):
        release.finalize(finalizing.stage, finalizing.receipt, freezer, SNAPSHOT_DATE)
    assert finalizing.calls == [] and finalizing.publication == []


def test_finalize_holds_the_committed_references_before_any_other_check(
    finalizing, monkeypatch
):
    """Review r1, M13 (Z P3-2): every finalize of a completed freeze holds the
    committed references to the release's first, whether or not the timing
    record changed, and a refusal there stops it before any other check."""
    with pytest.raises(SystemExit, match="requires the publication check's record"):
        release.finalize(finalizing.stage, finalizing.receipt, freezer, SNAPSHOT_DATE)
    assert finalizing.references == [
        (release.ROOT / release.SNAPSHOT, driver.release_exclusions_sha256())
    ]
    assert driver.release_exclusions_sha256() == sha(release_text().encode())

    def refuse(snapshot, sha256):
        raise SystemExit("frozen reference scenarios.csv does not match its pin")

    monkeypatch.setattr(release, "verify_committed_references", refuse)
    finalizing.changed.extend([TIMING, "uv.lock"])
    (finalizing.stage / "stage.json").write_text(json.dumps({"early": True}))
    with pytest.raises(SystemExit, match="does not match its pin"):
        release.finalize(finalizing.stage, finalizing.receipt, freezer, SNAPSHOT_DATE)
    assert finalizing.calls == [] and finalizing.publication == []


def test_finalize_refuses_a_rehearsal_stage(finalizing):
    (finalizing.stage / "stage.json").write_text(
        json.dumps({"early": True, "partial": False})
    )
    with pytest.raises(SystemExit, match="cannot become a release"):
        release.finalize(finalizing.stage, finalizing.receipt, freezer, SNAPSHOT_DATE)


# --- The freeze of the no-build stage, through the real gates (review r1, M4) -
#
# Terra's end-to-end harness (tests/test_freeze_terra.py, "The freeze of an
# installed-build stage"), ported to this release's path, which installs no
# reference build. The stage below is written by the driver's own steps where
# they run offline: write_release_exclusions as --step install-exclusions
# records it, seed_digest, adjudicate_exclusions (the d2180 entry), triage
# (the real collect_audit, record gates and annotation writer),
# write_judge_provenance and export (its pins, inputs, provenance, roster,
# both scope checks and the real dashboard validator). release.main then runs
# every one of its gates on that stage, and the tests at the end of the
# section freeze it.
#
# MOCK, each set where named: a run for the new model (an answer for every
# one of the 1,984 outputs, each the reference but the ruled output's, timed
# 2026-11-08 UTC); an incumbent's wrong answers on the 63 cases release
# 20261027's record decides, with seed verdicts classed as each decision
# records its judge; the seed digest those verdicts give, in place of the
# committed one; the ruled case's Opus 5.5 verdict, its sidecar and
# transcript; the spec's two days; the input pins, as if committed at HEAD;
# release 20261027's payload (synthetic modelStats under the real 51-model
# roster); the boards export_full_run and release_20261006.export_payload
# return (scope checks (a) and (b) hold on them); the incumbent's base
# prediction rows; and freeze_snapshot.main with the serving and registry
# lookups it makes (_h_freezer_main writes what the freezer writes, from
# where the freeze configured it). None of these values is a board-run
# result.
#
# Review r2, N1: a second template (h_template_kept) carries the ruled case
# over. There, MOCK, the incumbent also answers the ruled output wrong, the
# seed carries that case with a verdict judged before the ruling, the new
# model answers it right and opens one undecided case instead (H_OTHER_CASE,
# judged by Opus 5.5 on v2), and release 20261027's payload carries the
# incumbent's ruled cell as the base's annotations give it, while the
# exporters' boards carry it as the staged annotations give it.

import io  # noqa: E402
import shutil  # noqa: E402

import release_20261006  # noqa: E402

H_NEW = driver.MODELS["fable52"]
H_SLUG = "fable52"
H_INCUMBENT = "claude-fable-5"
H_STAGE = Path("results/local/fable52-stage")
BUNDLE = Path("publish") / RUN
H_BOARD = f"data-board{release.BOARD_MODELS}.json"
H_RUN = "fable52-runs/fable52"
H_RULED_CASE = f"us__{RULED[0]}__{RULED[1]}"
# MOCK: the new model's first request, 2026-11-08 10:00 UTC; its rows are
# timed from here, so the response window ends that day.
H_ANSWERED = 1794132000.0
H_WINDOW = f"{freezer.MODEL_RESPONSE_START} to 2026-11-08"
H_JUDGED_AT = "2026-11-09T12:00:00+00:00"
# MOCK: the kept board's carried verdict of the ruled case, judged before the
# 2026-11-01 ruling.
H_CARRIED_AT = "2026-10-20T12:00:00+00:00"
H_ROWS, H_NOTES = release.ANNOTATION_CSVS
H_AMENDMENTS = release.COMMITTED_AMENDMENTS
EXPLANATIONS = release.EXPLANATIONS
H_COLUMNS = (
    "model",
    "scenario_id",
    "variable",
    "prediction",
    "explanation",
    "raw_response",
    "provider_resolved_model",
    "prompt_tokens",
    "completion_tokens",
    "error",
    "estimated_cost_usd",
    "total_cost_usd",
    "total_tokens",
    "live_calls",
    "cache_hit_calls",
    "live_elapsed_seconds",
    "elapsed_seconds",
    "request_started_at",
    "request_completed_at",
)
# configure_freezer assigns these on the freeze_snapshot module itself; each
# test puts them back.
H_CONFIGURED = (
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
# MOCK usage for the incumbent whose usage export carries from the base.
H_FABLE5_USAGE = {
    "costUsd": 12.5,
    "costPerHousehold": 0.125,
    "totalTokens": 1000000,
    "latencySeconds": 30.25,
}


def h_blob(path) -> bytes:
    """A file of release 20261027's tree (BASE_COMMIT), read once."""
    return base_blob(Path(path))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


@functools.cache
def _h_fingerprint() -> str:
    """The treatment the registry gives Claude Fable 5.2 (validate_treatment's
    expected), as its run state records it."""
    captured = []

    def capture(fingerprint, expected, **kwargs):
        captured.append(expected)

    original = freezer._validate_treatment_fingerprint
    freezer._validate_treatment_fingerprint = capture
    try:
        release.validate_treatment(
            freezer,
            {"model": H_NEW, "treatment_fingerprint": {}},
            Path("run_state.json"),
            REPO / FROZEN / "scenarios.csv",
        )
    finally:
        freezer._validate_treatment_fingerprint = original
    return json.dumps({"fingerprint_version": 3, **captured[0]})


def h_fingerprint() -> dict:
    return json.loads(_h_fingerprint())


def _h_stat(model: str, exact: float, n: int, **usage) -> dict:
    return {
        "model": model,
        "condition": "no_tools",
        "score": exact,
        "exact": exact,
        "n": n,
        "nParsed": n - 5,
        **usage,
    }


def _h_cell(prediction: float, truth: float, **fields) -> dict:
    return {
        "prediction": prediction,
        "groundTruth": truth,
        "thresholdScore": 100.0 if prediction == truth else 0.0,
        **fields,
    }


def _h_country(
    stats: list[dict], records: list[dict], ruled: dict | None, kept: bool = False
) -> dict:
    """A board the real dashboard validator accepts, wrong answers annotated:
    one unruled output, and the ruled output with a cell for every model,
    scored unless ``ruled`` (the d2180 record) excludes it. MOCK: on the
    ruled output the new model answers wrong; with ``kept``, the incumbent
    does instead, its cell's annotation fields left to _h_annotate_ruled."""
    from policybench.analysis import _reference_exclusion_payload
    from policybench.reference_exclusions import exclusion_basis

    moved = (
        {"scored": True}
        if ruled is None
        else {
            "scored": False,
            "excludedReason": str(ruled["reason_code"]),
            "excludedInput": exclusion_basis(ruled),
        }
    )
    cells = {}
    for row in stats:
        model = row["model"]
        if kept and model == H_INCUMBENT:
            cells[model] = _h_cell(1000.0, 0.0, **moved)
        elif model == H_NEW and not kept:
            cells[model] = _h_cell(
                1000.0,
                0.0,
                failureSource="prompt_ambiguity",
                failureSubtype="state_local_rule",
                **moved,
            )
        else:
            cells[model] = _h_cell(0.0, 0.0, **moved)
    return {
        "country": "us",
        "scenarios": {
            household: {
                "country": "us",
                "state": state,
                "numAdults": 1,
                "numChildren": 0,
            }
            for household, state in (("scenario_000", "CA"), (RULED[0], "MN"))
        },
        "modelStats": stats,
        "programStats": [{"variable": "snap", "score": 50.0}],
        "heatmap": [],
        "scenarioPredictions": {
            "scenario_000": {
                "snap": {
                    H_INCUMBENT: _h_cell(
                        900.0,
                        1200.0,
                        failureSource="llm_error",
                        failureSubtype="thresholds_rates",
                        scored=True,
                    ),
                    H_NEW: _h_cell(1200.0, 1200.0, scored=True),
                }
            },
            RULED[0]: {RULED[1]: cells},
        },
        "failureModes": {"programs": [], "households": []},
        "referenceExclusions": [
            _reference_exclusion_payload(record) for record in records
        ],
    }


def _h_boards(kept: bool = False) -> SimpleNamespace:
    """MOCK release 20261027's payload and the exporters' boards: synthetic
    modelStats for the real incumbent roster and Claude Fable 5.2, on the
    base's record (the scope export) and the release's (export_full_run).
    With ``kept``, _h_country's kept ruled cells."""
    incumbents = sorted(release.base_serving_config()["models"])
    scored = driver.RELEASE_SCORED + driver.NEW_EXCLUSIONS
    live_stats = [
        _h_stat(model, 40.0 + index * 0.5, scored, costUsd=1.25)
        for index, model in enumerate(incumbents)
        if model != H_INCUMBENT
    ]
    live_stats.append(_h_stat(H_INCUMBENT, 47.5, scored, **H_FABLE5_USAGE))
    new = _h_stat(H_NEW, 45.25, scored, costUsd=0.5)
    base = json.loads(h_blob(FROZEN / release.EXCLUSIONS))["exclusions"]
    records = release_record()["exclusions"]
    (ruled,) = [r for r in records if driver.spec_key(r) == RULED]
    released = copy.deepcopy([*live_stats, new])
    for row in released:
        row["n"] -= driver.NEW_EXCLUSIONS
    # export_full_run reports none of the carried usage: the incumbent's rows
    # record none of it.
    for key in driver.CARRIED_USAGE[H_INCUMBENT]:
        del next(r for r in released if r["model"] == H_INCUMBENT)[key]
    scope = _h_country(copy.deepcopy([*live_stats, new]), base, None, kept)
    # Release 20261027's payload: the scope export without the new model's
    # rows, as check (a) requires (review r1, M9).
    live = copy.deepcopy(scope)
    live["modelStats"] = live_stats
    live["heatmap"] = [row for row in live["heatmap"] if row["model"] != H_NEW]
    for variables in live["scenarioPredictions"].values():
        for models in variables.values():
            del models[H_NEW]
    return SimpleNamespace(
        live={"countries": {"us": live}},
        exports={
            "release": {
                "countries": {"us": _h_country(released, records, ruled, kept)}
            },
            "scope": {"countries": {"us": scope}},
        },
    )


def _h_point_freeze_at(workspace: Path, mp) -> None:
    """The freeze and the freezer both write into ``workspace`` only."""
    mp.setattr(release, "ROOT", workspace)
    mp.setattr(freezer, "ROOT", workspace)
    mp.setattr(freezer, "SNAPSHOT_DIR", workspace / release.SNAPSHOT)
    mp.setattr(freezer, "RUN_DEST", workspace / FROZEN)
    mp.setattr(freezer, "ANNOTATIONS_DEST", workspace / release.ANNOTATIONS)
    mp.setattr(
        freezer, "PUBLIC_PAPER_PDF", workspace / "app/public/paper/policybench.pdf"
    )
    mp.setattr(freezer, "PUBLIC_PAPER_WEB_DIR", workspace / "app/public/paper/web")
    mp.setattr(freezer, "APP_PAPER_SNAPSHOT", workspace / "app/src/paperSnapshot.json")


def _h_serving_from_the_registry(board):
    """What freeze_serving_configuration writes in a checkout without the
    historical run directories: every incumbent registry-backed, and Claude
    Fable 5.2 backed by its run state (or, with the ``new_registry`` defect,
    not)."""

    def freeze(destination: Path) -> None:
        base = json.loads(h_blob(release.SNAPSHOT / "model_serving_config.json"))
        serving = copy.deepcopy(base)
        for row in serving["models"].values():
            row["evidence"] = {"kind": "registry"}
        kind = "registry" if "new_registry" in board.defects else "run_state"
        serving["models"][H_NEW] = {
            **copy.deepcopy(base["models"][H_INCUMBENT]),
            "provider_id": h_fingerprint()["model_id"],
            "evidence": {"kind": kind, "run": "somewhere/else"},
        }
        serving["evidence_summary"] = {"registry": len(base["models"]), kind: 1}
        serving["registry_commit"] = "the freezer's commit"
        destination.write_text(json.dumps(serving, indent=2, sort_keys=True) + "\n")

    return freeze


def _h_freezer_main(board):
    """Stand-in for freeze_snapshot.main: it writes what the freezer writes,
    from where the freeze configured it (freeze_run, the serving rows,
    freeze_annotations, freeze_committed_artifacts and build_manifest), with
    ``board.defects`` applied, and records the configuration it found. No
    build is installed, so the freezer keeps the committed manifest's
    reference pins (configure_freezer sets REFERENCE_PINS to None)."""

    def main() -> None:
        defects = board.defects
        board.calls.append(
            {
                name: getattr(freezer, name)
                for name in (
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
        for name in (
            "scenarios.csv",
            "scenarios.csv.meta.json",
            driver.CSV_NAME,
            driver.EXCLUSIONS_NAME,
        ):
            freezer.copy_exact(freezer.SOURCE_US / name, run / name)
        if "other_reference" in defects:
            with (run / driver.CSV_NAME).open("a") as stream:
                stream.write("\n")
        (run / driver.META_NAME).write_bytes(freezer.REFERENCE_META_SOURCE.read_bytes())
        committed_csv = freezer.SNAPSHOT_DIR / "us_reference_outputs.csv"
        freezer.copy_exact(freezer.SOURCE_US / driver.CSV_NAME, committed_csv)
        if "other_csv_copy" in defects:
            with committed_csv.open("a") as stream:
                stream.write("\n")
        if "other_exclusions" in defects:
            doc = json.loads((run / driver.EXCLUSIONS_NAME).read_text())
            doc["exclusions"][-2]["frozen_value"] += 1
            (run / driver.EXCLUSIONS_NAME).write_text(driver.exclusions_text(doc))
        if "base_exclusions" in defects:
            (run / driver.EXCLUSIONS_NAME).write_bytes(
                h_blob(FROZEN / driver.EXCLUSIONS_NAME)
            )
        freezer.gzip_deterministic(
            freezer.SOURCE_US / "predictions.csv",
            run / "predictions.csv.gz",
            stored_name="predictions.csv",
        )
        if "other_predictions" in defects:
            (run / "predictions.csv.gz").write_bytes(b"other predictions")
        serving = freezer.SNAPSHOT_DIR / "model_serving_config.json"
        freezer.freeze_serving_configuration(serving)
        if "serving_row" in defects:
            rows = json.loads(serving.read_text())
            rows["models"][H_INCUMBENT]["request_timeout_seconds"] += 1
            serving.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n")
        destination = freezer.ANNOTATIONS_DEST
        kept = (destination / driver.ADJUDICATIONS).read_bytes()
        shutil.rmtree(destination)
        destination.mkdir(parents=True)
        if "other_record" in defects:
            kept += b"\n"
        (destination / driver.ADJUDICATIONS).write_bytes(kept)
        for name in (H_ROWS, H_NOTES, EXPLANATIONS):
            freezer.copy_exact(freezer.SOURCE_ANNOTATIONS / name, destination / name)
        if "extra_annotation" in defects:
            (destination / "notes.txt").write_text("Left behind.\n")
        manifest = json.loads(h_blob(release.SNAPSHOT / "manifest.json"))
        manifest["description"] = manifest["description"].replace(
            manifest["snapshot_date"], freezer.SNAPSHOT_DATE
        )
        manifest["snapshot_date"] = freezer.SNAPSHOT_DATE
        manifest["reference_output_refresh"] = freezer.read_reference_refresh()
        manifest["committed_snapshot_artifacts"]["us_reference_outputs.csv"] = (
            freezer.sha256_file(committed_csv)
        )
        manifest["scope"]["models"] = release.BOARD_MODELS - ("models_51" in defects)
        manifest["model_response_date"] = (
            f"{freezer.MODEL_RESPONSE_START} to 2026-11-07"
            if "window" in defects
            else window
        )
        records = json.loads((run / driver.EXCLUSIONS_NAME).read_text())["exclusions"]
        manifest["reference_exclusions"]["outputs"] = len(records)
        manifest["reference_exclusions"]["scored_outputs_per_model"] = (
            driver.BASE_OUTPUTS - len(records)
        )
        manifest["published_dashboard_artifact"] = freezer.PUBLISHED_DASHBOARD_ARTIFACT
        pointer = json.loads((freezer.ROOT / release.POINTER).read_text())
        manifest["live_dashboard_artifact"].update(
            {key: pointer[key] for key in ("tag", "asset", "url", "sha256", "bytes")}
        )
        files = manifest["source_run_artifacts"][RUN]["files"]
        assert freezer.REFERENCE_PINS is None
        for name in (driver.CSV_NAME, driver.EXCLUSIONS_NAME, "predictions.csv.gz"):
            files[name] = freezer.sha256_file(run / name)
        committed = manifest["committed_snapshot_artifacts"]
        committed["model_serving_config.json"] = freezer.sha256_file(serving)
        audit = manifest["audit_annotation_artifacts"]["files"]
        for name in (driver.ADJUDICATIONS, H_ROWS, H_NOTES, EXPLANATIONS):
            audit[name] = freezer.sha256_file(destination / name)
        if "outside" in defects:
            manifest["population_weight_artifact"]["sha256"] = "0" * 64
        if "pinned_reference" in defects:
            files["scenarios.csv"] = "0" * 64
        if "explanations_pin" in defects:
            audit[EXPLANATIONS] = "0" * 64
        if "refresh" in defects:
            manifest["reference_output_refresh"]["policyengine_us_version"] = "2.41.0"
        manifest["rendered_paper_artifacts"] = freezer.rendered_paper_artifacts()
        (freezer.SNAPSHOT_DIR / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
        freezer.write_app_paper_snapshot(manifest)

    return main


def _h_patch(mp, workspace: Path, board) -> None:
    """Point the driver, the freeze and the freezer at ``workspace`` and at the
    MOCK sources the section's comment names."""
    import pandas as pd

    import policybench.full_run_export

    def blob(path):
        # Review r3, Q1: MOCK release 20261027's committed annotation files
        # (_h_base_files), once the stage writer has built them.
        found = board.base_files.get(Path(path))
        return base_blob(Path(path)) if found is None else found

    mp.setattr(driver, "base_commit_blob", blob)
    _h_point_freeze_at(workspace, mp)
    mp.setattr(driver, "SPEC_PATH", workspace / SPEC_PATH)
    mp.setattr(driver, "JUDGE_PROVENANCE", workspace / driver.JUDGE_PROVENANCE_PATH)
    mp.setattr(driver, "INPUT_PINS", workspace / driver.INPUT_PINS_PATH)
    head = driver.head_blob
    mp.setattr(
        driver,
        "head_blob",
        lambda path: board.committed.get(str(path)) or head(path),
    )
    if board.seed_sha256:
        mp.setattr(driver, "SEED_DIGEST_SHA256", board.seed_sha256)
    mp.setattr(driver, "base_payload_from_commit", lambda: copy.deepcopy(board.live))

    def export_full_run(run_dir, *, countries, skip_app_data):
        assert countries == ["us"] and skip_app_data
        board.reads.append(Path(run_dir))
        (Path(run_dir) / "data.json").write_text("export_full_run's own payload\n")
        (Path(run_dir) / "us/data.json").write_text(
            "export_full_run's country payload\n"
        )
        analysis = Path(run_dir) / "us/analysis"
        analysis.mkdir(exist_ok=True)
        (analysis / "metrics.csv").write_text("model,score\nsynthetic,1\n")
        payload = copy.deepcopy(board.exports["release"])
        if board.kept:
            _h_annotate_ruled(payload, Path(run_dir) / "annotations")
        return payload

    def export_payload(bundle, base, exclusions=None, **kwargs):
        assert exclusions is not None
        payload = copy.deepcopy(board.exports["scope"])
        if board.kept:
            _h_annotate_ruled(payload, Path(bundle) / "annotations")
        return payload

    mp.setattr(policybench.full_run_export, "export_full_run", export_full_run)
    mp.setattr(release_20261006, "export_payload", export_payload)
    mp.setattr(
        release,
        "base_prediction_rows",
        lambda: pd.read_csv(io.StringIO(board.baseline), low_memory=False),
    )
    for name in H_CONFIGURED:
        mp.setattr(freezer, name, getattr(freezer, name))
    mp.setattr(
        freezer, "freeze_serving_configuration", _h_serving_from_the_registry(board)
    )
    mp.setattr(freezer, "_serving_registry_commit", lambda serving: "f" * 40)
    mp.setattr(freezer, "main", _h_freezer_main(board))


def engine_pins(workspace: Path, version: str = driver.BASE_ENGINE) -> None:
    (workspace / "pyproject.toml").write_text(
        f'[project]\ndependencies = ["policyengine-us=={version}"]\n'
    )
    (workspace / "uv.lock").write_text(
        '[[package]]\nname = "policyengine-us"\n'
        f'version = "{version}"\n'
        '[[package]]\nname = "policybench"\nversion = "0.1.0"\n'
        "[package.metadata]\nrequires-dist = ["
        f'{{name = "policyengine-us", specifier = "=={version}"}}]\n'
    )


def _h_write_checkout(workspace: Path) -> None:
    """The checkout as release 20261027 left it, from git: its snapshot,
    annotations, pointer, version list and held-reference record, and the
    dependencies pinned to its engine; the filled spec (MOCK days)."""
    engine_pins(workspace)
    snapshot = workspace / release.SNAPSHOT
    names = [release.SNAPSHOT / name for name in ("manifest.json",)]
    names += [release.SNAPSHOT / "model_serving_config.json"]
    names += [FROZEN / name for name in driver.BASE_REFERENCE_SHA256]
    names += [
        release.ANNOTATIONS / name for name in (*driver.ANNOTATION_FILES, H_AMENDMENTS)
    ]
    names += [release.POINTER, release.VERSIONS]
    names += [Path("reference_audit/held_references.json")]
    names += list(driver.BASE_REPOSITORY_INPUT_FILES)
    for name in names:
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(h_blob(name))
    timing = workspace / driver.REPOSITORY_INPUT_FILES[2]
    timing.parent.mkdir(parents=True, exist_ok=True)
    timing.write_bytes((REPO / driver.REPOSITORY_INPUT_FILES[2]).read_bytes())
    paper = workspace / "app/public/paper"
    (paper / "web").mkdir(parents=True)
    (paper / "policybench.pdf").write_bytes(b"synthetic rendered PDF\n")
    (paper / "web/index.html").write_text("<p>Synthetic paper</p>\n")
    (paper / "web/style.css").write_text("p { color: black; }\n")
    (snapshot / "us_reference_outputs.csv").write_bytes(
        h_blob(FROZEN / driver.CSV_NAME)
    )
    spec = workspace / SPEC_PATH
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(json.dumps(filled_spec(), indent=2) + "\n")


def _h_csv(rows) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    for row in rows:
        writer.writerow(row)
    return stream.getvalue()


def _h_decided_cases() -> dict[str, dict]:
    """Release 20261027's decisions, by case id."""
    return {
        driver.case_id(entry): entry
        for entry in driver.base_adjudication_record()["adjudications"]
    }


def _h_verdict(source: str, subtype: str, suspect: bool, model: str) -> dict:
    return {
        "reference_suspect": suspect,
        "reference_bug_hypothesis": "",
        "case_failure_source": source,
        "case_failure_subtype": subtype,
        "rationale": "The model applied the rule this case turns on incorrectly.",
        "models": [
            {
                "model": model,
                "failure_source": source,
                "failure_subtype": subtype,
                "diagnosis": "The model applied an outdated threshold.",
            }
        ],
    }


# The cell fields the exporter writes from the row annotation and the case
# note (policybench.analysis.build_dashboard_payload), and their columns.
H_ROW_FIELDS = {
    "annotation": "annotation",
    "failureSource": "failure_source",
    "failureSubtype": "failure_subtype",
}
H_CASE_FIELDS = {
    "caseAnnotation": "case_annotation",
    "caseFailureSources": "case_failure_sources",
    "caseFailureSubtypes": "case_failure_subtypes",
}


def _h_ruled_fields(rows, cases) -> dict:
    """The MOCK incumbent's annotation fields on the ruled output, from row
    annotations and case notes as triage writes them (stripped text, as the
    exporter writes it on a wrong cell)."""
    row = rows[
        (rows.scenario_id == RULED[0])
        & (rows.variable == RULED[1])
        & (rows.model == H_INCUMBENT)
    ]
    note = cases[(cases.scenario_id == RULED[0]) & (cases.variable == RULED[1])]
    assert len(row) == len(note) == 1
    fields = {k: str(row.iloc[0][c]).strip() for k, c in H_ROW_FIELDS.items()}
    fields.update({k: str(note.iloc[0][c]).strip() for k, c in H_CASE_FIELDS.items()})
    return fields


def _h_annotate_ruled(payload: dict, annotations: Path) -> None:
    """The kept board's ruled incumbent cell, its annotation fields read from
    the bundle's annotations, as the exporter reads them."""
    import pandas as pd

    fields = _h_ruled_fields(
        pd.read_csv(annotations / H_ROWS), pd.read_csv(annotations / H_NOTES)
    )
    cell = payload["countries"]["us"]["scenarioPredictions"][RULED[0]][RULED[1]]
    cell[H_INCUMBENT].update(fields)


# Review r3, Q1: MOCK release 20261027's committed wording amendments, each
# rewording text a MOCK seed verdict gives (_h_verdict): the H_INCUMBENT row's
# diagnosis and the case note's rationale.
H_BASE_REWORDS = {
    "annotation": ("an outdated threshold.", "a threshold an earlier year set."),
    "case_annotation": ("incorrectly.", "incorrectly (MOCK committed wording)."),
}
H_BASE_ROW = "The model applied a threshold an earlier year set."
H_BASE_NOTE = (
    "The model applied the rule this case turns on incorrectly (MOCK committed "
    "wording)."
)


def _h_base_reworded(board) -> list[str]:
    """The cases MOCK release 20261027's committed amendments reword: the
    first decided case, and on the kept board the ruled case too."""
    first = min(_h_decided_cases())
    return [first, H_RULED_CASE] if board.kept else [first]


def _h_base_files(stage: Path, board, opened: str) -> dict[Path, bytes]:
    """MOCK: release 20261027's committed row annotations, case notes and
    wording amendments record, by path, as its triage left them for the MOCK
    seed: collect_audit's frames on every case but ``opened`` (which the new
    model opens), the MOCK committed amendments (H_BASE_REWORDS) on each case
    _h_base_reworded names, then release 20261027's 63 decisions."""
    from policybench.adjudications import apply_adjudications
    from policybench.audit import collect_audit

    collected = collect_audit(stage / BUNDLE / "us", stage / "audit")
    rows, cases = (
        frame[
            [
                f"us__{s}__{v}" != opened
                for s, v in zip(frame.scenario_id, frame.variable, strict=True)
            ]
        ].copy()
        for frame in (collected["row"], collected["case"])
    )
    cases = cases.rename(
        columns={
            "case_failure_source": "case_failure_sources",
            "case_failure_subtype": "case_failure_subtypes",
        }
    )
    amendments = [
        {
            "case_id": case,
            "field": field,
            **({"model": H_INCUMBENT} if field == "annotation" else {}),
            "old": old,
            "new": new,
            "reason": "MOCK: a committed wording amendment.",
        }
        for case in _h_base_reworded(board)
        for field, (old, new) in H_BASE_REWORDS.items()
    ]
    driver.amend_annotations(rows, cases, amendments)
    rows, cases, _ = apply_adjudications(rows, cases, driver.base_adjudications())
    record = {
        "note": "MOCK: release 20261027's wording amendments for the MOCK seed.",
        "amendments": amendments,
    }
    return {
        release.ANNOTATIONS / H_ROWS: driver.annotation_csv_text(rows).encode(),
        release.ANNOTATIONS / H_NOTES: driver.annotation_csv_text(cases).encode(),
        release.ANNOTATIONS / H_AMENDMENTS: release.amendments_text(record).encode(),
    }


def _h_base_ruled_fields(board) -> dict:
    """The kept stage's ruled incumbent cell as release 20261027's committed
    files (MOCK, _h_base_files) give it: the ruled row and note a MOCK
    committed amendment rewords, d2180's decision not applied."""
    import pandas as pd

    return _h_ruled_fields(
        *(
            pd.read_csv(io.BytesIO(board.base_files[release.ANNOTATIONS / name]))
            for name in (H_ROWS, H_NOTES)
        )
    )


def _h_other_case(reference: list[dict]) -> str:
    """The kept board's one opened case: the first undecided output of the
    ruled variable on another household (MOCK)."""
    decided = _h_decided_cases()
    return min(
        case
        for row in reference
        if row["variable"] == RULED[1] and row["scenario_id"] != RULED[0]
        for case in [f"us__{row['scenario_id']}__{row['variable']}"]
        if case not in decided
    )


def _h_judge_ruled_case(audit: Path, case_id: str = H_RULED_CASE) -> None:
    """The ruled case, which the new model opens on the MOCK board (or, on
    the kept board, ``case_id``), judged by Opus 5.5 on v2: a MOCK verdict
    with its full sidecar and a clean transcript."""
    from policybench.judge_template import template_header

    case = audit / "cases" / case_id
    case.mkdir(parents=True)
    prompt = template_header(driver.JUDGE_TEMPLATE_VERSION) + (
        f"\nClassify the synthetic wrong answer on {case_id}.\n"
    )
    (case / "prompt.md").write_text(prompt)
    verdict = _h_verdict("llm_error", "thresholds_rates", False, H_NEW)
    write_json(case / "verdict.json", verdict)
    write_json(
        case / "verdict.meta.json",
        {
            "verdict_sha256": sha(case / "verdict.json"),
            "prompt_sha256": sha(case / "prompt.md"),
            "judge_template_version": driver.JUDGE_TEMPLATE_VERSION,
            "judge_model_requested": driver.JUDGE_MODEL,
            "judge_model_reported": [driver.JUDGE_MODEL],
            "judge_runner": driver.JUDGE_RUNNER,
            "judged_at_utc": H_JUDGED_AT,
            "judge_effort": "xhigh",
            "judge_isolation": {"tools": "none (--tools '')"},
            "judge_auth": {"method": "oauth_token", "account": None, "org": None},
            "judge_account_declared": next(iter(driver.PROVENANCE_GROUPS)),
        },
    )
    events = [
        {"type": "user", "message": {"content": prompt}},
        {
            "type": "assistant",
            "effort": "xhigh",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "answer-1",
                        "name": "StructuredOutput",
                        "input": verdict,
                    }
                ]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "answer-1",
                        "content": "done",
                    }
                ]
            },
        },
    ]
    (case / "claude.transcript.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events)
    )


def _h_write_stage(workspace: Path, board) -> Path:
    """The stage prepare, bind-seed and install-exclusions leave: release
    20261027's references in the scoring source and the bundle, then the
    release's exclusion record installed (write_release_exclusions); the
    base's explanations and adjudication record; Claude Fable 5.2's run and
    the bundle's predictions; the seed audit and the ruled case's verdict;
    stage.json, model-provenance.json and prompt-changes.json; and the input
    pins."""
    from policybench.audit import AUDIT_OUTPUT_SCHEMA
    from policybench.judge_template import template_header

    stage = workspace / H_STAGE
    bundle = stage / BUNDLE
    us, annotations, scoring = bundle / "us", bundle / "annotations", stage / "scoring"
    for directory in (us, annotations, scoring):
        directory.mkdir(parents=True)
    for target in (us, scoring):
        for name in driver.BASE_REFERENCE_SHA256:
            (target / name).write_bytes(h_blob(FROZEN / name))
    for name in (driver.ADJUDICATIONS, EXPLANATIONS):
        (annotations / name).write_bytes(h_blob(release.ANNOTATIONS / name))
    # On the MOCK board the new model answers right on every output but the
    # ruled one, and the incumbent wrong on every decided case. On the kept
    # board the incumbent answers the ruled output wrong too, and the new
    # model answers it right and answers H_OTHER_CASE wrong.
    with (us / driver.CSV_NAME).open(newline="") as stream:
        reference = list(csv.DictReader(stream))
    decided = _h_decided_cases()
    board.other_case = _h_other_case(reference) if board.kept else None
    opened = board.other_case if board.kept else H_RULED_CASE
    new = []
    for index, row in enumerate(reference):
        started = H_ANSWERED + index * 0.5
        value = row["value"]
        if f"us__{row['scenario_id']}__{row['variable']}" == opened:
            value = str(float(value) + 1000.0)
        new.append(
            [
                H_NEW,
                row["scenario_id"],
                row["variable"],
                value,
                "Synthetic answer.",
                "{}",
                H_NEW,
                900,
                40,
                "",
                "0.0001",
                "0.0001",
                940,
                1,
                0,
                "2.5",
                "2.5",
                f"{started:.1f}",
                f"{started + 2.5:.1f}",
            ]
        )
    wrong = []
    carried = {H_RULED_CASE} if board.kept else set()
    for row in reference:
        if f"us__{row['scenario_id']}__{row['variable']}" in {*decided, *carried}:
            prediction = float(row["value"]) + 1000.0
            wrong.append(
                [H_INCUMBENT, row["scenario_id"], row["variable"], prediction]
                + ["Synthetic wrong answer."]
                + [""] * (len(H_COLUMNS) - 5)
            )
    inputs = stage / "inputs" / H_SLUG
    inputs.mkdir(parents=True)
    (inputs / "predictions.csv").write_text(_h_csv([H_COLUMNS, *new]))
    write_json(
        inputs / "run_state.json",
        {
            "model": H_NEW,
            "total": 100,
            "completed": 100,
            "stopped_reason": None,
            "treatment_fingerprint": h_fingerprint(),
        },
    )
    (us / "predictions.csv").write_text(_h_csv([H_COLUMNS, *wrong, *new]))
    board.baseline = _h_csv([H_COLUMNS, *wrong])
    # MOCK: the seed audit, one kept case per decided output, each verdict
    # classed as its decision records the judge.
    audit = stage / "audit"
    (audit / "cases").mkdir(parents=True)
    write_json(audit / "schema.json", AUDIT_OUTPUT_SCHEMA)
    manifest = []
    for case, entry in sorted(decided.items()):
        verdict = _h_verdict(
            entry["judge_failure_source"],
            entry["judge_failure_subtype"],
            bool(entry.get("judge_reference_suspect")),
            H_INCUMBENT,
        )
        _, scenario, variable = case.split("__")
        manifest.append(
            {
                "case_id": case,
                "scenario_id": scenario,
                "variable": variable,
                "wrong_models": [H_INCUMBENT],
                "parse_failure_only": False,
            }
        )
        directory = audit / "cases" / case
        directory.mkdir()
        (directory / "prompt.md").write_text(
            template_header(1) + f"\nClassify the wrong answers on {case}.\n"
        )
        write_json(directory / "verdict.json", verdict)
        write_json(
            directory / "verdict.meta.json",
            {"verdict_sha256": sha(directory / "verdict.json")},
        )
    if board.kept:
        # MOCK: the ruled case carried over, judged before the ruling.
        manifest.append(
            {
                "case_id": H_RULED_CASE,
                "scenario_id": RULED[0],
                "variable": RULED[1],
                "wrong_models": [H_INCUMBENT],
                "parse_failure_only": False,
            }
        )
        directory = audit / "cases" / H_RULED_CASE
        directory.mkdir()
        (directory / "prompt.md").write_text(
            template_header(1) + f"\nClassify the wrong answers on {H_RULED_CASE}.\n"
        )
        write_json(
            directory / "verdict.json",
            _h_verdict("llm_error", "credit_phaseout", False, H_INCUMBENT),
        )
        write_json(
            directory / "verdict.meta.json",
            {
                "verdict_sha256": sha(directory / "verdict.json"),
                "judge_model_requested": driver.JUDGE_MODEL,
                "judge_model_reported": [driver.JUDGE_MODEL],
                "judged_at_utc": H_CARRIED_AT,
            },
        )
    seed = driver.seed_digest(audit)
    board.seed_sha256 = hashlib.sha256(
        driver.seed_digest_text(seed).encode()
    ).hexdigest()
    # The case only the new model answers wrong on the MOCK board (the ruled
    # one; on the kept board, H_OTHER_CASE): added.
    _h_judge_ruled_case(audit, opened)
    _, scenario, variable = opened.split("__")
    manifest.append(
        {
            "case_id": opened,
            "scenario_id": scenario,
            "variable": variable,
            "wrong_models": [H_NEW],
            "parse_failure_only": False,
        }
    )
    manifest.sort(key=lambda item: item["case_id"])
    (audit / "cases.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in manifest)
    )
    # Review r3, Q1: MOCK release 20261027's committed annotation files, which
    # _h_patch serves at BASE_COMMIT, and the checkout's copies of them.
    board.base_files = _h_base_files(stage, board, opened)
    for path, content in board.base_files.items():
        (workspace / path).write_bytes(content)
    driver.write_json(
        stage / driver.PROMPT_CHANGES,
        {"kept": sorted(seed), "changed": [], "added": [opened]},
    )
    prepared = {
        "partial": False,
        "early": False,
        "base_tag": driver.BASE_TAG,
        "base_commit": driver.BASE_COMMIT,
        "files": {},
        "seed": seed,
    }
    prepared["exclusions_installed"] = driver.write_release_exclusions(stage)
    names = [BUNDLE / "us" / n for n in (*driver.REFERENCE_FILES, "predictions.csv")]
    names += [BUNDLE / "annotations" / EXPLANATIONS]
    names += [Path("inputs") / H_SLUG / n for n in driver.PINNED_INPUTS]
    prepared["files"] = {str(name): sha(stage / name) for name in names}
    driver.write_json(stage / "stage.json", prepared)
    _h_stamp_inputs(stage, board)
    return stage


def _h_stamp_inputs(stage: Path, board, *, repin=True) -> None:
    """model-provenance.json for the staged run and, with ``repin``, the input
    pins naming its files, written and committed (board.committed)."""
    inputs = stage / "inputs" / H_SLUG
    state = json.loads((inputs / "run_state.json").read_text())
    driver.write_json(
        stage / "model-provenance.json",
        {
            H_NEW: {
                "predictions_sha256": sha(inputs / "predictions.csv"),
                "treatment_fingerprint": state["treatment_fingerprint"],
            }
        },
    )
    if not repin:
        return
    record = {
        "inputs": {
            H_SLUG: {
                "run": f"{H_RUN}/run",
                "sha256": {name: sha(inputs / name) for name in driver.PINNED_INPUTS},
            }
        }
    }
    blob = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode()
    path = release.ROOT / driver.INPUT_PINS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    board.committed[driver.INPUT_PINS_PATH] = blob


def _h_build_template(tmp_path_factory, kept: bool) -> SimpleNamespace:
    """The releasable stage, built once: install-exclusions' record, the real
    adjudicate-exclusions, triage, write_judge_provenance and export (section
    comment), on MOCK release 20261027 committed annotation files
    (_h_base_files). With ``kept``, the kept board's, and before export
    release 20261027's payload takes those files' annotation fields on the
    ruled incumbent cell (_h_base_ruled_fields)."""
    boards = _h_boards(kept)
    board = SimpleNamespace(
        live=boards.live,
        exports=boards.exports,
        committed={},
        seed_sha256=None,
        baseline=None,
        reads=[],
        calls=[],
        defects=set(),
        kept=kept,
        other_case=None,
        base_files={},
    )
    workspace = tmp_path_factory.mktemp("h-template-kept" if kept else "h-template")
    workspace = workspace / "workspace"
    workspace.mkdir()
    with pytest.MonkeyPatch.context() as mp:
        _h_patch(mp, workspace, board)
        _h_write_checkout(workspace)
        stage = _h_write_stage(workspace, board)
        mp.setattr(driver, "SEED_DIGEST_SHA256", board.seed_sha256)
        # Today's UTC date is the MOCK written day: no test depends on the clock.
        mp.setattr(driver, "utc_today", lambda: WRITTEN_ON)
        args = SimpleNamespace(stage_dir=stage, partial=False, early=False)
        driver.adjudicate_exclusions(args)
        driver.triage(args, stage / BUNDLE)
        driver.write_judge_provenance(args)
        if kept:
            cells = board.live["countries"]["us"]["scenarioPredictions"]
            cells[RULED[0]][RULED[1]][H_INCUMBENT].update(_h_base_ruled_fields(board))
        driver.export(args, stage / BUNDLE, copy.deepcopy(board.live))
        # The driver reads its committed inputs from REPO while the writable
        # checkout lives here. Bind the actual freeze inputs here.
        receipt_path = stage / "release-ready.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["repository_inputs"] = driver.repository_input_hashes(workspace)
        driver.write_json(receipt_path, receipt)
    board.reads.clear()
    return SimpleNamespace(workspace=workspace, board=board)


@pytest.fixture(scope="module")
def h_template(tmp_path_factory):
    """The releasable stage, the ruled case re-opened (_h_build_template)."""
    return _h_build_template(tmp_path_factory, kept=False)


@pytest.fixture(scope="module")
def h_template_kept(tmp_path_factory):
    """The releasable stage, the ruled case carried over (review r2, N1)."""
    return _h_build_template(tmp_path_factory, kept=True)


@pytest.fixture
def h_stage(h_template, tmp_path, monkeypatch):
    """A copy of the releasable stage and its checkout, the driver, the freeze
    and the freezer pointed at it."""
    return _h_stage_from(h_template, tmp_path, monkeypatch)


@pytest.fixture
def h_stage_kept(h_template_kept, tmp_path, monkeypatch):
    """h_stage on the template that carries the ruled case over."""
    return _h_stage_from(h_template_kept, tmp_path, monkeypatch)


def _h_stage_from(template, tmp_path, monkeypatch) -> SimpleNamespace:
    workspace = tmp_path / "workspace"
    shutil.copytree(template.workspace, workspace)
    board = copy.deepcopy(template.board)
    _h_patch(monkeypatch, workspace, board)
    stage = workspace / H_STAGE

    def files():
        return {
            path.relative_to(workspace): path.read_bytes()
            for path in workspace.rglob("*")
            if path.is_file()
        }

    def rebind(*, restamp=True, repin=False):
        """Every hash follows the stage as it now stands: the receipt's and,
        with ``restamp``, stage.json's and model-provenance.json's (the input
        pins too, with ``repin``)."""
        if restamp:
            prepared = json.loads((stage / "stage.json").read_text())
            prepared["files"] = {name: sha(stage / name) for name in prepared["files"]}
            driver.write_json(stage / "stage.json", prepared)
            _h_stamp_inputs(stage, board, repin=repin)
        receipt = json.loads((stage / "release-ready.json").read_text())
        # As a re-export would bind them: the files that still exist.
        receipt["files"] = {
            name: sha(stage / name)
            for name in receipt["files"]
            if (stage / name).is_file()
        }
        receipt["payload_sha256"] = sha(stage / H_BOARD)
        receipt["judge_provenance"]["sha256"] = sha(driver.JUDGE_PROVENANCE)
        driver.write_json(stage / "release-ready.json", receipt)

    def run(*options):
        release.main(["--stage-dir", str(stage), *options])

    return SimpleNamespace(
        workspace=workspace,
        stage=stage,
        board=board,
        files=files,
        rebind=rebind,
        run=run,
    )


def _h_json(path: Path) -> dict:
    return json.loads(path.read_text())


def test_the_releasable_stage_passes_every_gate_and_a_dry_run_writes_nothing(
    h_stage, capsys
):
    before = h_stage.files()
    h_stage.run("--dry-run")
    assert h_stage.files() == before
    assert h_stage.board.calls == []
    out = capsys.readouterr().out
    assert f"Validated local release inputs: {driver.RELEASE_TAG}, 52 models" in out
    assert "references unchanged; 50 exclusions (1 new)" in out
    assert "0 adjudications added beyond the spec's; 0 wording amendments" in out
    assert f"model responses {H_WINDOW}; snapshot {SNAPSHOT_DATE}; nothing" in out
    assert (
        "Dating step: the record the freeze commits holds decisions on 1 "
        "re-opened case, which date_fable52_judge_verdicts.py restates: "
        f"{H_RULED_CASE}\n"
    ) in out


@pytest.mark.parametrize("state", ["reopened", "kept"])
def test_the_dry_runs_dating_line_is_the_dating_steps_own_finding(
    request, capsys, state
):
    """Review r2, N4 (R P3-4): the dry run says, before the freeze writes,
    what the dating step will find. With the ruled case re-opened it names
    the one case the step's restatements restate; with it carried over
    (only an undecided case re-opened) it says the step stops, and the
    step's restatements, run on the record the freeze commits and the bound
    provenance, stop there."""
    h_stage = request.getfixturevalue("h_stage_kept" if state == "kept" else "h_stage")
    stage = h_stage.stage
    before = h_stage.files()
    h_stage.run("--dry-run")
    assert h_stage.files() == before
    line = capsys.readouterr().out.splitlines()[-1]
    record = _h_json(stage / BUNDLE / "annotations" / release.ADJUDICATIONS)
    if state == "kept":
        assert line.startswith(
            "Dating step: the record the freeze commits holds no decision on a "
            "re-opened case, and date_fable52_judge_verdicts.py stops on that"
        )
        assert "rule on the saved relaxation patch before the freeze" in line
        with pytest.raises(
            SystemExit, match="no committed decision is on a re-opened case"
        ):
            dating.restatements(stage, record)
    else:
        assert line.endswith(f"restates: {H_RULED_CASE}")
        assert list(dating.restatements(stage, record)["cases"]) == [H_RULED_CASE]


def test_the_record_gate_checks_the_ruled_verdicts_day_again(h_stage):
    """Review r1, M16 (E F4): a staged record whose date conventions and spec
    agree on a written day before the ruled case's MOCK verdict (judged
    2026-11-09) is refused at the freeze; on the verdict's own day it
    passes. Before M16 the freeze took both."""
    stage = h_stage.stage
    staged = stage / "publish" / RUN / "annotations" / release.ADJUDICATIONS
    spec_path = h_stage.workspace / SPEC_PATH
    rejudged = driver.rejudged_cases(stage)
    gate = (
        staged,
        stage / "publish" / RUN / "us",
        rejudged,
        driver.load_amendments(stage, rejudged),
        stage / "audit" / "cases",
    )
    entry = json.loads(staged.read_text())["adjudications"][-1]
    assert (driver.case_id(entry), entry["judged_on_utc"]) == (
        H_RULED_CASE,
        H_JUDGED_AT[:10],
    )

    def written_on(day: str) -> None:
        spec = json.loads(spec_path.read_text())
        spec["adjudications_written_on"] = day
        spec_path.write_text(json.dumps(spec, indent=2) + "\n")
        record = json.loads(staged.read_text())
        record["date_conventions"] = driver.release_date_conventions(
            driver.base_adjudication_record()["date_conventions"]
        )
        staged.write_text(driver.record_text(record))

    written_on(H_JUDGED_AT[:10])
    assert release.verify_adjudication_record(*gate) == 0
    written_on("2026-11-08")
    with pytest.raises(SystemExit, match="precedes the day of a verdict"):
        release.verify_adjudication_record(*gate)


def _h_payload(h_stage) -> dict:
    return _h_json(h_stage.stage / H_BOARD)


def _h_write_payload(h_stage, payload: dict) -> None:
    (h_stage.stage / H_BOARD).write_text(driver.payload_text(payload))


def _h_refused(h_stage, message, modes=((), ("--dry-run",)), error=SystemExit):
    """Each mode of the freeze refuses with ``message`` and writes nothing."""
    before = h_stage.files()
    for mode in modes:
        with pytest.raises(error, match=message) as refused:
            h_stage.run(*mode)
        assert h_stage.files() == before
    assert h_stage.board.calls == []
    return refused


def _h_pointer(stage: Path) -> dict:
    payload = stage / H_BOARD
    tag = driver.RELEASE_TAG
    return {
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


def test_the_freeze_writes_the_release(h_stage, capsys):
    """The pointer and version list, the frozen run's references (release
    20261027's) and the release's exclusion record, the committed copy of the
    reference outputs, the annotations (the staged record and CSVs, the
    base's explanations and its amendments record), the serving rows, the
    manifest's statements, and the predictions asset and cache."""
    stage, root = h_stage.stage, h_stage.workspace
    payload = stage / H_BOARD
    h_stage.run()
    assert f"Built {driver.RELEASE_TAG} locally" in capsys.readouterr().out
    # Review r2, N4: the freeze rewrites the receipt and keeps the provenance
    # binding the dating step reads.
    assert dating.bound_provenance(stage) == _h_json(driver.JUDGE_PROVENANCE)
    pointer = _h_pointer(stage)
    assert (root / release.POINTER).read_text() == (
        json.dumps(pointer, indent=2, sort_keys=True) + "\n"
    )
    versions = _h_json(root / release.VERSIONS)
    previous = json.loads(h_blob(release.VERSIONS))
    live = next(v for v in versions["versions"] if v["id"] == versions["default"])
    assert live["snapshotLabel"] == f"Snapshot {SNAPSHOT_DATE}"
    assert live["description"].endswith(" - 52 models")
    assert [v for v in versions["versions"] if v is not live] == [
        v for v in previous["versions"] if v["id"] != previous["default"]
    ]
    frozen = root / FROZEN
    for name, pin in driver.BASE_REFERENCE_SHA256.items():
        if name != driver.EXCLUSIONS_NAME:
            assert sha(frozen / name) == pin, name
    assert (frozen / driver.EXCLUSIONS_NAME).read_text() == release_text()
    assert (
        sha(root / release.SNAPSHOT / "us_reference_outputs.csv")
        == (driver.BASE_REFERENCE_SHA256[driver.CSV_NAME])
    )
    annotations = root / release.ANNOTATIONS
    assert sorted(p.name for p in annotations.iterdir()) == sorted(
        (driver.ADJUDICATIONS, H_ROWS, H_NOTES, EXPLANATIONS, H_AMENDMENTS)
    )
    staged = stage / BUNDLE / "annotations"
    for name in (driver.ADJUDICATIONS, H_ROWS, H_NOTES, EXPLANATIONS):
        assert (annotations / name).read_bytes() == (staged / name).read_bytes()
    record = _h_json(annotations / driver.ADJUDICATIONS)
    assert len(record["adjudications"]) == 64
    assert driver.spec_key(record["adjudications"][-1]) == RULED
    assert (annotations / EXPLANATIONS).read_bytes() == h_blob(
        release.ANNOTATIONS / EXPLANATIONS
    )
    # Review r3, Q1: release 20261027's record, here the MOCK base's.
    assert (annotations / H_AMENDMENTS).read_bytes() == h_stage.board.base_files[
        release.ANNOTATIONS / H_AMENDMENTS
    ]
    serving = _h_json(root / release.SNAPSHOT / "model_serving_config.json")
    base = release.base_serving_config()
    for model, row in base["models"].items():
        assert serving["models"][model] == row
    assert serving["models"][H_NEW]["evidence"] == {"kind": "run_state", "run": H_RUN}
    assert serving["evidence_summary"] == {
        "registry": base["evidence_summary"]["registry"],
        "run_state": base["evidence_summary"]["run_state"] + 1,
    }
    assert serving["registry_commit"] == "f" * 40
    manifest = _h_json(root / release.SNAPSHOT / "manifest.json")
    assert manifest["snapshot_date"] == SNAPSHOT_DATE
    assert manifest["scope"]["models"] == 52
    assert manifest["model_response_date"] == H_WINDOW
    assert manifest["reference_exclusions"]["outputs"] == 50
    assert manifest["reference_exclusions"]["scored_outputs_per_model"] == 1934
    artifact = {key: pointer[key] for key in ("tag", "asset", "url", "sha256", "bytes")}
    assert manifest["published_dashboard_artifact"] == artifact
    base_manifest = json.loads(h_blob(release.SNAPSHOT / "manifest.json"))
    assert release.manifest_problems(base_manifest, manifest) == []
    [configured] = h_stage.board.calls
    assert configured["SNAPSHOT_DATE"] == SNAPSHOT_DATE
    assert configured["SOURCE_RUN"] == stage / BUNDLE
    assert configured["SOURCE_ANNOTATIONS"] == staged
    assert configured["REFERENCE_META_SOURCE"] == (
        stage / BUNDLE / "us" / driver.META_NAME
    )
    assert configured["REFERENCE_PINS"] is None
    assert configured["PUBLISHED_DASHBOARD_SOURCE"] == payload
    assert configured["PUBLISHED_DASHBOARD_ARTIFACT"] == artifact
    assert configured["RUN_STATE_EVIDENCE"] == {
        H_NEW: str(stage / "inputs" / H_SLUG / "run_state.json")
    }
    assert configured["AUDIT_CASES_DIR"] == stage / "audit/cases"
    assert (stage / "predictions.csv.gz").read_bytes() == (
        frozen / "predictions.csv.gz"
    ).read_bytes()
    cache = root / "app/.cache" / f"dashboard-data-{sha(payload)[:16]}.json"
    assert cache.read_bytes() == payload.read_bytes()
    receipt = _h_json(stage / "release-ready.json")
    assert set(receipt["repository_postfreeze"]) == {
        str(release.SNAPSHOT / "manifest.json"),
        str(release.VERSIONS),
    }


def test_freezing_twice_writes_the_same_files(h_stage):
    """A second freeze of the same stage finds this release's record where
    release 20261027's was, and writes the same bytes."""
    h_stage.run()
    first = h_stage.files()
    h_stage.run()
    assert h_stage.files() == first


def test_the_rebuild_reads_a_scratch_copy_of_the_bound_bundle(h_stage):
    """export_full_run writes into the bundle it reads, so the freeze's
    rebuild hands it a scratch copy outside the checkout and removes it."""
    h_stage.run("--dry-run")
    reads = h_stage.board.reads
    assert len(reads) == 1
    assert not reads[0].is_relative_to(h_stage.workspace)
    assert not reads[0].exists()


# What the freezer writes outside the release. Terra's defects that the
# no-build path still has, with each check's message: the references and the
# committed copy one byte off (Terra froze the base's in place of its build;
# here the base's are the release's), and the base's 49-record exclusion
# record frozen in place of the release's 50. With no build, the explanations
# pin and the refresh record stay release 20261027's, so a change to either
# lands among the manifest's changes outside the release; Terra's build
# stated both.
H_FREEZER_DEFECTS = {
    "other_exclusions": (
        r"frozen reference reference_exclusions\.json does not match its pin"
    ),
    "base_exclusions": (
        r"frozen reference reference_exclusions\.json does not match its pin"
    ),
    "other_reference": (
        r"frozen reference reference_outputs\.csv does not match its pin"
    ),
    "other_csv_copy": r"Frozen us_reference_outputs\.csv is not release 20261027's",
    "other_record": f"The frozen {re.escape(driver.ADJUDICATIONS)} is not the staged",
    "extra_annotation": r"Frozen annotation files are not the release's: \['notes",
    "serving_row": (
        f"Frozen serving configuration: .*{H_INCUMBENT} is not release 20261027's"
    ),
    "new_registry": f"Missing frozen run-state evidence for {re.escape(H_NEW)}$",
    "outside": (
        r"changes outside the release: \['population_weight_artifact\.sha256'\]$"
    ),
    "pinned_reference": (
        r"changes outside the release: \['source_run_artifacts\.[^']+"
        r"\.files\.scenarios\.csv'\]$"
    ),
    "explanations_pin": (
        r"changes outside the release: \['audit_annotation_artifacts\.files\."
        f"{re.escape(EXPLANATIONS)}'\\]$"
    ),
    "models_51": r"does not state the release: \{'scope\.models': 51\}$",
    "window": (
        r"does not state the release: \{'model_response_date': "
        f"'{freezer.MODEL_RESPONSE_START} to 2026-11-07'\\}}$"
    ),
    "refresh": (
        r"changes outside the release: "
        r"\['reference_output_refresh\.policyengine_us_version'\]$"
    ),
    "other_predictions": "The predictions asset is not the frozen predictions",
}


@pytest.mark.parametrize("defect", H_FREEZER_DEFECTS)
def test_the_freeze_refuses_what_the_freezer_wrote_outside_the_release(h_stage, defect):
    """Each defect stops the freeze at its own check. The receipt then
    records no completed freeze, so finalize refuses the stage."""
    h_stage.board.defects.add(defect)
    with pytest.raises(SystemExit, match=H_FREEZER_DEFECTS[defect]):
        h_stage.run()
    assert "repository_postfreeze" not in _h_json(h_stage.stage / "release-ready.json")
    with pytest.raises(SystemExit, match="Finalize requires a completed freeze"):
        h_stage.run("--finalize")


# Review r1, M13 (Z P3-2): edits between the freeze and finalize to what the
# freeze committed, and what finalize answers.
H_COMMITTED_EDITS = {
    **{
        name: (
            FROZEN / name,
            f"frozen reference {re.escape(name)} does not match its pin",
        )
        for name in driver.REFERENCE_FILES
        if name != driver.EXCLUSIONS_NAME
    },
    "the base's record": (
        FROZEN / driver.EXCLUSIONS_NAME,
        f"frozen reference {re.escape(driver.EXCLUSIONS_NAME)} does not match",
    ),
    "us_reference_outputs.csv": (
        release.SNAPSHOT / "us_reference_outputs.csv",
        "Frozen us_reference_outputs.csv is not release 20261027's",
    ),
}


@pytest.mark.parametrize("edit", [None, *H_COMMITTED_EDITS])
def test_finalize_refuses_a_committed_reference_edited_after_the_freeze(h_stage, edit):
    """The review's case: a committed reference edited between the freeze
    and --finalize. Untouched, finalize passes the check and stops where the
    publication check has not run."""
    h_stage.run()
    if edit is None:
        message = "requires the publication check's record"
    else:
        relative, message = H_COMMITTED_EDITS[edit]
        path = h_stage.workspace / relative
        if edit == "the base's record":
            path.write_bytes(h_blob(relative))
        else:
            path.write_bytes(path.read_bytes() + b"\n")
    before = h_stage.files()
    with pytest.raises(SystemExit, match=message):
        h_stage.run("--finalize")
    assert h_stage.files() == before


def _h_frozen_arguments(h_stage) -> dict:
    root = h_stage.workspace
    serving = release.base_serving_config()
    return dict(
        stage=h_stage.stage,
        snapshot=root / release.SNAPSHOT,
        annotations=root / release.ANNOTATIONS,
        exclusions_sha256=driver.release_exclusions_sha256(),
        pointer=_h_json(root / release.POINTER),
        window=H_WINDOW,
        snapshot_date=SNAPSHOT_DATE,
        previous_serving=serving,
        incumbents=set(serving["models"]),
        runs={H_SLUG: H_RUN},
    )


H_FROZEN_CHANGES = {
    "window": (
        lambda _: {"window": f"{freezer.MODEL_RESPONSE_START} to 2026-11-07"},
        "model_response_date",
    ),
    "date": (lambda _: {"snapshot_date": "2026-11-11"}, "'snapshot_date'"),
    "run": (
        lambda _: {"runs": {H_SLUG: "fable52-runs/elsewhere"}},
        "evidence names run 'fable52-runs/fable52'",
    ),
    "pointer": (
        lambda _: {
            "pointer": {"tag": "x", "asset": "x", "url": "x", "sha256": "x", "bytes": 1}
        },
        "published_dashboard_artifact",
    ),
    "base_exclusion_pin": (
        lambda _: {
            "exclusions_sha256": driver.BASE_REFERENCE_SHA256[driver.EXCLUSIONS_NAME]
        },
        r"frozen reference reference_exclusions\.json does not match its pin",
    ),
    "incumbent_dropped": (
        lambda arguments: {"incumbents": arguments["incumbents"] - {H_INCUMBENT}},
        f"roster differs on \\['{H_INCUMBENT}'\\]",
    ),
}


@pytest.mark.parametrize("change", H_FROZEN_CHANGES)
def test_verify_frozen_checks_the_release_the_freeze_derived(h_stage, change):
    """After a freeze, verify_frozen passes on what it wrote and refuses
    another window, snapshot date, supervised run or artifact than the freeze
    derived, release 20261027's exclusion pin in place of the release's, and
    an incumbent roster short of one."""
    h_stage.run()
    arguments = _h_frozen_arguments(h_stage)
    release.verify_frozen(**arguments)
    edit, message = H_FROZEN_CHANGES[change]
    with pytest.raises(SystemExit, match=message):
        release.verify_frozen(**{**arguments, **edit(arguments)})


def test_verify_frozen_refuses_an_amendments_record_the_freeze_did_not_write(
    h_stage,
):
    """The committed amendments record is release 20261027's with the stage's
    list (empty here) appended; one byte more is refused."""
    h_stage.run()
    arguments = _h_frozen_arguments(h_stage)
    path = arguments["annotations"] / H_AMENDMENTS
    path.write_bytes(path.read_bytes() + b" ")
    message = f"The frozen {re.escape(H_AMENDMENTS)} is not release 20261027's record"
    with pytest.raises(SystemExit, match=message):
        release.verify_frozen(**arguments)


# The refusals that must come before any write, through main: each stops the
# freeze and its dry run with the checkout untouched and the freezer never
# called. Ported from Terra's harness where the no-build path keeps the gate;
# the stage's own build gate and the release's exclusion record are new.


@pytest.mark.parametrize(
    "build", ["reference-build", "reference-install.json", "references_installed"]
)
def test_a_stage_that_records_a_build_is_refused_before_any_write(h_stage, build):
    """The no-build path's own gate: a stage holding either of the install's
    files, or whose stage.json records installed references (its receipt hash
    following), came from another driver."""
    stage = h_stage.stage
    if build == "reference-build":
        (stage / build).mkdir()
        (stage / build / driver.CSV_NAME).write_text("scenario_id\n")
    elif build == "reference-install.json":
        driver.write_json(stage / build, {})
    else:
        prepared = _h_json(stage / "stage.json")
        prepared[build] = {"sha256": {}}
        driver.write_json(stage / "stage.json", prepared)
        h_stage.rebind(restamp=False)
    _h_refused(h_stage, "the stage records an installed reference build")


@pytest.mark.parametrize(
    "name, message",
    [
        (
            str(driver.BASE_REPOSITORY_INPUT_FILES[0]),
            "Repository input changed from the base release: policybench/bench",
        ),
        (
            str(driver.BASE_REPOSITORY_INPUT_FILES[1]),
            "Repository input changed from the base release: policybench/popul",
        ),
        ("pyproject.toml", r"changed since strict export: \['pyproject\.toml'\]$"),
        ("uv.lock", r"changed since strict export: \['uv\.lock'\]$"),
        (
            str(driver.REPOSITORY_INPUT_FILES[2]),
            r"changed since strict export: \['reference_audit/[^']+/sweep_timing",
        ),
    ],
)
def test_a_repository_input_changed_after_export_is_refused_before_any_write(
    h_stage, name, message
):
    path = h_stage.workspace / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((path.read_bytes() if path.is_file() else b"") + b"\n")
    _h_refused(h_stage, message)


def test_a_historical_version_entry_changed_is_refused_before_any_write(h_stage):
    path = h_stage.workspace / release.VERSIONS
    versions = _h_json(path)
    (entry,) = [v for v in versions["versions"] if v["id"] != versions["default"]][:1]
    entry["description"] += " Edited."
    path.write_text(json.dumps(versions, indent=2) + "\n")
    _h_refused(h_stage, "Historical data.versions.json entries changed")


@pytest.mark.parametrize("form", ["base", "release"])
def test_a_claim_in_the_live_description_is_refused_before_any_write(h_stage, form):
    """Review r1, M12 (Z P3-1), the review's case end to end: the claim is in
    data.versions.json before export, so the receipt binds it, and
    verify_repository_inputs frees the live description. The working tree
    holds release 20261027's text, or this release's from a first freeze."""
    path = h_stage.workspace / release.VERSIONS
    versions = _h_json(path)
    if form == "release":
        versions = release.release_versions(
            versions, release_record()["exclusions"], SNAPSHOT_DATE
        )
    live(versions)["description"] = live(versions)["description"].replace(*CLAIM)
    path.write_text(json.dumps(versions, indent=2) + "\n")
    receipt_path = h_stage.stage / "release-ready.json"
    receipt = _h_json(receipt_path)
    receipt["repository_inputs"] = driver.repository_input_hashes(h_stage.workspace)
    driver.write_json(receipt_path, receipt)
    _h_refused(h_stage, NEITHER)


@pytest.mark.parametrize("record", ["base", "edited"])
def test_a_staged_exclusion_record_not_the_releases_is_refused_before_any_write(
    h_stage, record
):
    """The bundle's exclusion record, every stage hash following: release
    20261027's own 49 records, or the release's with the ruled record's
    frozen value moved."""
    path = h_stage.stage / BUNDLE / "us" / driver.EXCLUSIONS_NAME
    if record == "base":
        path.write_bytes(h_blob(FROZEN / driver.EXCLUSIONS_NAME))
    else:
        doc = json.loads(path.read_text())
        (ruled,) = [r for r in doc["exclusions"] if driver.spec_key(r) == RULED]
        ruled["frozen_value"] += 1
        path.write_text(driver.exclusions_text(doc))
    h_stage.rebind()
    _h_refused(
        h_stage,
        f"Staged {re.escape(driver.EXCLUSIONS_NAME)} is not release 20261027's "
        "record plus the 1 ruled record",
    )


def _h_kept_case(h_stage) -> str:
    """A seed case the stage keeps: decided by release 20261027's record, with
    only the incumbent wrong on it (MOCK)."""
    return sorted(_h_json(h_stage.stage / driver.PROMPT_CHANGES)["kept"])[0]


@pytest.mark.parametrize(
    "defect, message",
    [
        ("changed", "Staged evidence changed since strict export: audit/cases/"),
        ("outside_stage", r"Staged evidence changed since strict export: \.\./"),
        ("missing_hashes", "missing staged evidence hashes"),
        ("models", "Strict export receipt does not match"),
        ("partial", "Strict export receipt does not match"),
        ("partial_missing", "Strict export receipt does not match"),
        ("tag", "Strict export receipt does not match"),
        ("payload", "Strict export receipt does not match"),
        ("base_tag", "does not name release 20261027 as its base"),
        ("base_sha256", "does not name release 20261027 as its base"),
    ],
)
def test_the_freeze_refuses_a_receipt_that_does_not_identify_this_stage(
    h_stage, defect, message
):
    stage = h_stage.stage
    receipt = _h_json(stage / "release-ready.json")
    if defect == "changed":
        (stage / "audit/cases" / H_RULED_CASE / "verdict.json").write_text("{}\n")
    elif defect == "outside_stage":
        pointer = h_stage.workspace / release.POINTER
        receipt["files"][f"../../../{release.POINTER}"] = sha(pointer)
    elif defect == "missing_hashes":
        receipt["files"] = {}
    elif defect == "models":
        receipt["models"] = 51
    elif defect == "partial":
        receipt["partial"] = True
    elif defect == "partial_missing":
        del receipt["partial"]
    elif defect == "tag":
        receipt["release_tag"] = driver.BASE_TAG
    elif defect == "payload":
        payload = _h_payload(h_stage)
        payload["countries"]["us"]["heatmap"] = []
        (stage / H_BOARD).write_text(driver.payload_text(payload) + " ")
    elif defect == "base_tag":
        receipt["base_tag"] = "dashboard-data-20261014"
    else:
        receipt["base_sha256"] = "0" * 64
    driver.write_json(stage / "release-ready.json", receipt)
    _h_refused(h_stage, message)


def _h_required_evidence(h_stage) -> list[str]:
    names = [BUNDLE / "us" / n for n in (*driver.REFERENCE_FILES, "predictions.csv")]
    names += [
        BUNDLE / "annotations" / n
        for n in (driver.ADJUDICATIONS, H_ROWS, H_NOTES, EXPLANATIONS)
    ]
    names += [Path("inputs") / H_SLUG / n for n in driver.PINNED_INPUTS]
    names += [Path(n) for n in ("model-provenance.json", driver.PROMPT_CHANGES)]
    names += [Path("stage.json"), Path("audit/cases.jsonl"), Path("audit/schema.json")]
    for case in (_h_kept_case(h_stage), H_RULED_CASE):
        names += [
            Path("audit/cases") / case / n
            for n in ("prompt.md", "verdict.json", "verdict.meta.json")
        ]
    names.append(Path("audit/cases") / H_RULED_CASE / "claude.transcript.jsonl")
    return [str(name) for name in names]


def test_the_receipt_binds_every_file_a_release_gate_reads(h_stage):
    """Without its receipt entry, a staged file could be edited after export
    and its other hashes made to follow; the freeze refuses the missing
    entry, for every file a later gate relies on: the bundle's references,
    record, annotations and predictions, the new model's run files, the
    prepare-time hashes, and a kept and the newly judged case's evidence."""
    stage = h_stage.stage
    receipt = _h_json(stage / "release-ready.json")
    required = _h_required_evidence(h_stage)
    assert set(required) <= set(receipt["files"])
    before = h_stage.files()
    for name in required:
        unbound = copy.deepcopy(receipt)
        del unbound["files"][name]
        driver.write_json(stage / "release-ready.json", unbound)
        with pytest.raises(SystemExit, match="does not bind") as refused:
            h_stage.run("--dry-run")
        assert name in str(refused.value)
    driver.write_json(stage / "release-ready.json", receipt)
    assert h_stage.files() == before


@pytest.mark.parametrize("extra", ["transcript", "amendments"])
def test_a_transcript_or_amendment_list_in_the_stage_must_be_bound(h_stage, extra):
    """The provenance gate reads a judged case's transcript, and the record
    gates the listed wording amendments: either, present and unbound, could be
    edited after export."""
    stage = h_stage.stage
    if extra == "transcript":
        name = Path("audit/cases") / _h_kept_case(h_stage) / "claude.transcript.jsonl"
        assert not (stage / name).exists()
        (stage / name).write_text("{}\n")
    else:
        name = Path(driver.AMENDMENTS)
        (stage / name).write_text(json.dumps({"amendments": []}))
    _h_refused(h_stage, f"does not bind.*{re.escape(str(name))}")


def test_a_bound_bundle_file_edited_without_its_hashes_is_refused(h_stage):
    path = h_stage.stage / BUNDLE / "annotations" / H_NOTES
    path.write_text(path.read_text() + "\n")
    _h_refused(
        h_stage,
        f"Staged evidence changed since strict export: {re.escape(str(BUNDLE))}",
    )


@pytest.mark.parametrize("field", ["early", "partial"])
@pytest.mark.parametrize("value", [True, "missing", None, "false"], ids=repr)
def test_a_rehearsal_stage_rebound_after_export_is_refused_by_main(
    h_stage, field, value
):
    """An otherwise releasable stage whose stage.json marks it early or
    partial (or leaves the flag unset or not a boolean), with its receipt hash
    refreshed, is refused by the freeze and its dry run before either writes
    anything."""
    prepared = _h_json(h_stage.stage / "stage.json")
    if value == "missing":
        del prepared[field]
    else:
        prepared[field] = value
    driver.write_json(h_stage.stage / "stage.json", prepared)
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, "early/partial stage cannot become a release")


@pytest.mark.parametrize("defect", ["edited", "missing", "unbound", "other_path"])
def test_the_freeze_refuses_a_provenance_record_export_did_not_bind(h_stage, defect):
    record = driver.JUDGE_PROVENANCE
    receipt = _h_json(h_stage.stage / "release-ready.json")
    if defect == "edited":
        record.write_text(
            json.dumps({"note": "Every judge ran isolated.", "verdicts": []})
        )
    elif defect == "missing":
        record.unlink()
    elif defect == "unbound":
        del receipt["judge_provenance"]
    else:
        receipt["judge_provenance"]["path"] = "docs/elsewhere.json"
    driver.write_json(h_stage.stage / "release-ready.json", receipt)
    _h_refused(h_stage, "not the judge provenance record")


def test_a_rebound_provenance_record_must_still_describe_the_stage(h_stage):
    """A record edited after export, its receipt hash refreshed, must still
    be what the stage's sidecars give."""
    record = _h_json(driver.JUDGE_PROVENANCE)
    record["note"] += " Every verdict was also checked by hand."
    driver.JUDGE_PROVENANCE.write_text(json.dumps(record, indent=1) + "\n")
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, "note is not the one its entries give")


def _h_stat_index(country: dict, new: bool) -> int:
    return next(
        index
        for index, row in enumerate(country["modelStats"])
        if (row["model"] == H_NEW) == new
    )


def _h_edit_new_score(country: dict) -> list[str]:
    index = _h_stat_index(country, new=True)
    country["modelStats"][index].update(exact=100.0, score=100.0)
    at = f"payload.countries.us.modelStats[{index} {H_NEW}]"
    return [f"{at}.score", f"{at}.exact"]


def _h_edit_incumbent_cost(country: dict) -> list[str]:
    index = _h_stat_index(country, new=False)
    row = country["modelStats"][index]
    row["costUsd"] *= 2
    return [f"payload.countries.us.modelStats[{index} {row['model']}].costUsd"]


def _h_edit_case_class(country: dict) -> list[str]:
    case = country["scenarioPredictions"]["scenario_000"]["snap"][H_INCUMBENT]
    assert case["failureSource"] != "prompt_ambiguity"
    case["failureSource"] = "prompt_ambiguity"
    return [
        f"payload.countries.us.scenarioPredictions.scenario_000.snap.{H_INCUMBENT}"
        ".failureSource"
    ]


def _h_edit_exclusion_note(country: dict) -> list[str]:
    index = len(country["referenceExclusions"]) - 2
    country["referenceExclusions"][index]["note"] = "A note no record carries."
    return [f"payload.countries.us.referenceExclusions[{index}].note"]


H_PAYLOAD_EDITS = {
    "new_model_score": _h_edit_new_score,
    "incumbent_cost": _h_edit_incumbent_cost,
    "case_class": _h_edit_case_class,
    "exclusion_note": _h_edit_exclusion_note,
}


@pytest.mark.parametrize("edit", H_PAYLOAD_EDITS)
def test_the_freeze_refuses_a_payload_edited_after_export(h_stage, edit):
    """The receipt binds the payload by a hash beside it. The new model's
    score, an incumbent's cost, a case's class or an exclusion's text edited,
    with that hash refreshed, passes the schema, roster and count gates;
    export's own build from the bound bundle does not give it."""
    payload = _h_payload(h_stage)
    paths = H_PAYLOAD_EDITS[edit](payload["countries"]["us"])
    _h_write_payload(h_stage, payload)
    h_stage.rebind(restamp=False)
    refused = _h_refused(h_stage, "is not what export builds")
    for path in paths:
        assert repr(path) in str(refused.value)


def _h_build_arguments(stage, monkeypatch) -> dict:
    """The keyword arguments the freeze's dry run hands build_payload."""
    seen = {}
    build = driver.build_payload

    def spy(*args, **kw):
        seen.update(kw)
        return build(*args, **kw)

    monkeypatch.setattr(driver, "build_payload", spy)
    stage.run("--dry-run")
    return seen


def test_the_rebuild_hands_the_scope_check_the_cases_this_release_reopened(
    h_stage, monkeypatch
):
    """Review r1, M9, and review r2, N1: the freeze's rebuild passes
    rejudged_cases' cases (the ruled case, which this stage judged) and
    decided_cases' (the ruled case), as export did."""
    seen = _h_build_arguments(h_stage, monkeypatch)
    assert seen["reopened"] == driver.rejudged_cases(h_stage.stage)
    assert seen["reopened"] == frozenset({H_RULED_CASE})
    assert seen["decided"] == driver.decided_cases() == frozenset({H_RULED_CASE})


# Review r2, N1: the ruled case carried over (h_template_kept). Triage applies
# d2180's decision to the carried verdict's rows, so the MOCK incumbent's ruled
# cell in the scope export carries the decided classes and sentence, and
# release 20261027's carries the base's. Review r3, Q1: a MOCK committed
# amendment rewords the base's ruled row and note (_h_base_files), and triage
# carries that wording onto the kept case, so both cells carry it.


def _h_kept_cells(h_stage_kept) -> tuple[dict, dict]:
    """The MOCK incumbent's ruled cell in release 20261027's payload and in
    the scope export the stubbed exporter gives on the staged annotations."""
    scope = copy.deepcopy(h_stage_kept.board.exports["scope"])
    _h_annotate_ruled(scope, h_stage_kept.stage / BUNDLE / "annotations")
    live = h_stage_kept.board.live
    return tuple(
        payload["countries"]["us"]["scenarioPredictions"][RULED[0]][RULED[1]][
            H_INCUMBENT
        ]
        for payload in (live, scope)
    )


def test_the_kept_stage_carries_the_ruled_case_and_triage_decides_it(h_stage_kept):
    """The premise of the kept template: prompt-changes keeps the ruled case,
    the stage re-opens only H_OTHER_CASE, the release decides the ruled case,
    triage gave the incumbent's ruled row and the case note d2180's class and
    sentence, and the incumbent's ruled cell differs from release 20261027's
    in exactly the class fields and caseAnnotation."""
    import pandas as pd

    stage, other = h_stage_kept.stage, h_stage_kept.board.other_case
    changes = _h_json(stage / driver.PROMPT_CHANGES)
    assert H_RULED_CASE in changes["kept"]
    assert (changes["changed"], changes["added"]) == ([], [other])
    assert driver.rejudged_cases(stage) == frozenset({other})
    assert driver.decided_cases() == frozenset({H_RULED_CASE})
    annotations = stage / BUNDLE / "annotations"
    staged = _h_ruled_fields(
        pd.read_csv(annotations / H_ROWS), pd.read_csv(annotations / H_NOTES)
    )
    assert (staged["failureSource"], staged["failureSubtype"]) == (
        "prompt_ambiguity",
        "state_local_rule",
    )
    assert "Developer adjudication (2026-11-01)" in staged["caseAnnotation"]
    live, scope = _h_kept_cells(h_stage_kept)
    assert (live["failureSource"], live["failureSubtype"]) == (
        "llm_error",
        "credit_phaseout",
    )
    assert "Developer adjudication" not in live["caseAnnotation"]
    assert staged["annotation"] == live["annotation"] == H_BASE_ROW
    assert staged["caseAnnotation"].startswith(H_BASE_NOTE + " Developer adjudication")
    moved = {field for field in live if live[field] != scope.get(field)}
    assert moved == release_20261006.CLASS_CELL_FIELDS | {"caseAnnotation"}
    assert list(live) == list(scope)


def test_the_kept_stage_passes_every_gate_and_freezes(h_stage_kept, monkeypatch):
    """With the ruled case carried over, the freeze's rebuild hands the scope
    check no re-opened ruled case and the ruled case as decided, every gate
    passes, a dry run writes nothing and the freeze then writes."""
    before = h_stage_kept.files()
    seen = _h_build_arguments(h_stage_kept, monkeypatch)
    assert h_stage_kept.files() == before
    assert seen["reopened"] == frozenset({h_stage_kept.board.other_case})
    assert seen["decided"] == frozenset({H_RULED_CASE})
    h_stage_kept.run()
    assert h_stage_kept.files() != before


def test_without_the_decided_cases_check_a_refuses_the_kept_stage(
    h_stage_kept, monkeypatch
):
    """Holding every case to the base, the rule before review r2's N1, the
    freeze stops the kept stage at check (a) on the incumbent's ruled cell,
    before any write."""
    monkeypatch.setattr(driver, "decided_cases", lambda spec=None: frozenset())
    refused = _h_refused(h_stage_kept, "is not release 20261027's outside modelStats")
    cell = f"scenarioPredictions {RULED[0]} {RULED[1]} {H_INCUMBENT} changed"
    assert cell in str(refused.value)


@pytest.mark.parametrize("field", ["annotation", "referenceExplanation"])
def test_the_kept_rebuild_holds_the_ruled_cells_row_annotation(h_stage_kept, field):
    """On the ruled case decided and kept, release 20261027's row annotation
    and referenceExplanation still bind: with release 20261027's payload
    (MOCK) holding another than the one its committed files (MOCK) give the
    staged cell, check (a) stops the freeze, before any write."""
    live = h_stage_kept.board.live["countries"]["us"]["scenarioPredictions"]
    live[RULED[0]][RULED[1]][H_INCUMBENT][field] = "MOCK: a base wording."
    _h_refused(h_stage_kept, "is not release 20261027's outside modelStats")


def _h_staged_frames(h_stage) -> tuple:
    import pandas as pd

    return tuple(
        pd.read_csv(_h_annotations(h_stage) / name, dtype=str, keep_default_na=False)
        for name in (H_ROWS, H_NOTES)
    )


def _h_without(frame, cases) -> str:
    """``frame``'s CSV text without the rows on ``cases``."""
    keep = [
        f"us__{s}__{v}" not in cases
        for s, v in zip(frame.scenario_id, frame.variable, strict=True)
    ]
    return frame[keep].to_csv(index=False)


@pytest.mark.parametrize("board", ["h_stage", "h_stage_kept"])
def test_every_kept_case_carries_the_mock_committed_wording(request, board):
    """Review r3, Q1, on both MOCK boards: the staged row annotations and
    case notes carry the MOCK committed amendments' wording on each case
    they reword, beside the decisions; every kept case passes the kept-case
    gate; and both files are release 20261027's (MOCK) byte for byte outside
    the case the new model opens and the ruled case this release decides."""
    import pandas as pd

    from policybench.adjudications import load_adjudications

    h_stage = request.getfixturevalue(board)
    rows, notes = _h_staged_frames(h_stage)
    for case in _h_base_reworded(h_stage.board):
        rows_on = rows[
            [f"us__{s}__{v}" == case for s, v in zip(rows.scenario_id, rows.variable)]
        ]
        notes_on = notes[
            [f"us__{s}__{v}" == case for s, v in zip(notes.scenario_id, notes.variable)]
        ]
        assert rows_on.annotation.tolist() == [H_BASE_ROW]
        (note,) = notes_on.case_annotation
        assert note.startswith(H_BASE_NOTE + " Developer adjudication (")
    stage = h_stage.stage
    rejudged = driver.rejudged_cases(stage)
    decisions = load_adjudications(_h_annotations(h_stage) / driver.ADJUDICATIONS)
    assert driver.kept_annotation_problems(rows, notes, rejudged, decisions) == []
    skip = {*rejudged, H_RULED_CASE}
    for name, staged in zip((H_ROWS, H_NOTES), (rows, notes), strict=True):
        base = pd.read_csv(
            io.BytesIO(h_stage.board.base_files[release.ANNOTATIONS / name]),
            dtype=str,
            keep_default_na=False,
        )
        assert _h_without(staged, skip) == _h_without(base, skip)


@pytest.mark.parametrize("edit", ["class", "wording", "sentence"])
def test_export_stops_on_a_decided_kept_case_note_off_its_decision(h_stage_kept, edit):
    """Review r3, Q3: export holds the bundle's two annotation files to the
    staged record and to release 20261027's published wording (MOCK) before
    it builds. The ruled note, decided and kept, with its class, its MOCK
    committed wording or its adjudication sentence edited stops export
    before it writes anything."""
    import pandas as pd

    from policybench.adjudications import AdjudicationError

    stage = h_stage_kept.stage
    path = _h_annotations(h_stage_kept) / H_NOTES
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    mask = (frame.scenario_id == RULED[0]) & (frame.variable == RULED[1])
    note = frame.loc[mask, "case_annotation"].item()
    if edit == "class":
        frame.loc[mask, "case_failure_sources"] = "llm_error"
        error, message = AdjudicationError, "case note for .* carries"
    elif edit == "wording":
        frame.loc[mask, "case_annotation"] = note.replace(H_BASE_NOTE, "A MOCK note.")
        error, message = SystemExit, "a case this release keeps must carry"
    else:
        frame.loc[mask, "case_annotation"] = note.split(" Developer adjudication (")[0]
        error, message = AdjudicationError, "does not carry the recorded adjudication"
    path.write_text(frame.to_csv(index=False))
    before = h_stage_kept.files()
    args = SimpleNamespace(stage_dir=stage, partial=False, early=False)
    with pytest.raises(error, match=message):
        driver.export(args, stage / BUNDLE, copy.deepcopy(h_stage_kept.board.live))
    assert h_stage_kept.files() == before


def test_the_freeze_holds_every_kept_case_to_release_20261027s_files(h_stage):
    """Review r3, Q1: with a kept case's hypothesis in release 20261027's
    committed case notes (MOCK) other than the staged one, the freeze's
    rebuild still gives the staged bytes (the carry takes only the wording),
    and its kept-case gate stops the freeze and its dry run before any
    write, naming the cell."""
    import pandas as pd

    path = release.ANNOTATIONS / H_NOTES
    frame = pd.read_csv(
        io.BytesIO(h_stage.board.base_files[path]), keep_default_na=False
    )
    case = _h_kept_case(h_stage)
    _, scenario, variable = case.split("__")
    mask = (frame.scenario_id == scenario) & (frame.variable == variable)
    frame["reference_bug_hypothesis"] = frame["reference_bug_hypothesis"].astype(object)
    frame.loc[mask, "reference_bug_hypothesis"] = (
        "MOCK: a hypothesis the base published."
    )
    h_stage.board.base_files[path] = driver.annotation_csv_text(frame).encode()
    refused = _h_refused(
        h_stage,
        "a case this release keeps must carry the row annotations and case note",
    )
    assert f"{case} case note reference_bug_hypothesis" in str(refused.value)


def test_the_freeze_hands_the_annotation_gates_the_cases_this_release_reopened(
    h_stage, monkeypatch
):
    """Review r3, Q1: the freeze rebuilds the staged annotations
    (driver.annotation_frames) and runs the kept-case gate with
    rejudged_cases' cases (the ruled case, which the MOCK stage judged), as
    triage and export do. Release 20261027's files (MOCK) lack that case, so
    only the arguments show it."""
    seen = []
    build, gate = driver.annotation_frames, driver.verify_kept_annotations

    def build_spy(collected, rejudged, *rest):
        seen.append(("annotation_frames", rejudged))
        return build(collected, rejudged, *rest)

    def gate_spy(rows, cases, rejudged, decisions):
        seen.append(("verify_kept_annotations", rejudged))
        return gate(rows, cases, rejudged, decisions)

    monkeypatch.setattr(driver, "annotation_frames", build_spy)
    monkeypatch.setattr(driver, "verify_kept_annotations", gate_spy)
    h_stage.run("--dry-run")
    reopened = driver.rejudged_cases(h_stage.stage)
    assert reopened == frozenset({H_RULED_CASE})
    assert seen == [
        ("annotation_frames", reopened),
        ("verify_kept_annotations", reopened),
    ]


@pytest.mark.parametrize("case", ["ruled", "kept"])
def test_the_rebuild_lets_annotations_differ_only_on_reopened_cases(h_stage, case):
    """An incumbent's annotation in release 20261027's payload that the scope
    export does not give: on the ruled case, which this release re-opened,
    the freeze passes it; on another case it stops the freeze before any
    write, at check (a)."""
    scenario, variable = RULED if case == "ruled" else ("scenario_000", "snap")
    cell = h_stage.board.live["countries"]["us"]["scenarioPredictions"][scenario][
        variable
    ][H_INCUMBENT]
    cell["annotation"] = "MOCK: an annotation the base carried."
    if case == "ruled":
        h_stage.run("--dry-run")
    else:
        _h_refused(h_stage, "is not release 20261027's outside modelStats")


@pytest.mark.parametrize(
    "targets, message",
    [
        (
            ("release", "scope"),
            "with release 20261027's exclusion record, incumbent modelStats drift",
        ),
        (
            ("release",),
            "the release payload differs from the scope export beyond the ruled",
        ),
    ],
)
def test_the_scope_check_refuses_an_incumbent_the_record_does_not_explain(
    h_stage, targets, message
):
    """An incumbent's cost changed in what the exporters give, so that
    export's build gives the staged payload: with release 20261027's record
    put back it is not that release's (check a), and against the scope
    export the release's record does not explain it (check b)."""
    payload = _h_payload(h_stage)
    index = _h_stat_index(payload["countries"]["us"], new=False)
    model = payload["countries"]["us"]["modelStats"][index]["model"]
    for board in (payload, *(h_stage.board.exports[name] for name in targets)):
        (row,) = [
            r for r in board["countries"]["us"]["modelStats"] if r["model"] == model
        ]
        row["costUsd"] *= 2
    _h_write_payload(h_stage, payload)
    h_stage.rebind(restamp=False)
    refused = _h_refused(h_stage, message)
    assert model in str(refused.value)


@pytest.mark.parametrize("edit", ["no_heatmap", "unannotated_wrong_answer", "over_100"])
def test_the_real_dashboard_validator_refuses_the_staged_payload(h_stage, edit):
    payload = _h_payload(h_stage)
    country = payload["countries"]["us"]
    if edit == "no_heatmap":
        del country["heatmap"]
    elif edit == "unannotated_wrong_answer":
        del country["scenarioPredictions"]["scenario_000"]["snap"][H_INCUMBENT][
            "failureSource"
        ]
    else:
        country["programStats"][0]["score"] = 101.0
    _h_write_payload(h_stage, payload)
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, "Strict dashboard gate failed")


def _h_swap_exclusions(country):
    items = country["referenceExclusions"]
    items[0], items[1] = items[1], items[0]


H_ROSTER_EDITS = {
    "fifty_one_rows": (
        lambda country: country["modelStats"].pop(),
        "exactly 52 no-tools model rows",
    ),
    "tools_condition": (
        lambda country: country["modelStats"][3].update(condition="tools"),
        "exactly 52 no-tools model rows",
    ),
    "renamed_incumbent": (
        lambda country: country["modelStats"][_h_stat_index(country, new=False)].update(
            model="claude-impostor-1"
        ),
        "roster disagree",
    ),
    "scored_1935": (
        lambda country: country["modelStats"][-1].update(n=1935),
        "scored on 1934 outputs",
    ),
    "exclusions_swapped": (_h_swap_exclusions, "their order"),
}


@pytest.mark.parametrize("edit", H_ROSTER_EDITS)
def test_the_freeze_refuses_another_roster_or_scored_count(h_stage, edit):
    change, message = H_ROSTER_EDITS[edit]
    payload = _h_payload(h_stage)
    change(payload["countries"]["us"])
    _h_write_payload(h_stage, payload)
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, message)


def _h_unlisted_verdict(stage: Path) -> Path:
    """A synthetic unbound sidecar the historical whole-tree tally accepts."""
    case = stage / "audit/cases/us__extra__invented"
    write_json(case / "verdict.json", {})
    write_json(
        case / "verdict.meta.json",
        {
            "verdict_sha256": sha(case / "verdict.json"),
            "judge_model_requested": "invented-judge",
            "judge_model_reported": ["invented-judge"],
            "judge_runner": driver.JUDGE_RUNNER,
        },
    )
    return case


@pytest.mark.parametrize("operation", ["export", "freeze", "dry-run"])
def test_an_unlisted_verdict_added_after_export_is_refused_without_writes(
    h_stage, operation
):
    stage = h_stage.stage
    _h_unlisted_verdict(stage)
    before = h_stage.files()
    with pytest.raises(SystemExit, match="not manifest-listed judged cases"):
        if operation == "export":
            args = SimpleNamespace(stage_dir=stage, partial=False, early=False)
            driver.export(args, stage / BUNDLE, copy.deepcopy(h_stage.board.live))
        else:
            h_stage.run(*(["--dry-run"] if operation == "dry-run" else []))
    assert h_stage.files() == before
    assert h_stage.board.calls == []


def _h_rebind_verdict(case: Path) -> None:
    write_json(
        case / "verdict.meta.json",
        {
            **_h_json(case / "verdict.meta.json"),
            "verdict_sha256": sha(case / "verdict.json"),
        },
    )


@pytest.mark.parametrize(
    "defect, message",
    [
        ("edited_kept", "carried-over verdicts differ from the seed's"),
        ("other_models", "carried-over verdicts differ from the seed's"),
        ("unbound_sidecar", "carried-over verdicts differ from the seed's"),
        ("edited_prompt", "incumbent-only case prompts changed against the seed"),
        ("forged_partition", "prompt-changes.json disagrees with the stage's prompts"),
        ("other_seed", "audit seed is not release 20261027's"),
        ("seed_case_dropped", "seed cases vanished from the audit"),
    ],
)
def test_the_freeze_refuses_a_verdict_seed_or_partition_changed_after_export(
    h_stage, defect, message
):
    """Export validates the verdicts against the bound seed before it writes
    the receipt; the freeze does again. A kept verdict edited with its sidecar
    and every hash following, a prompt changed under it, a forged
    kept/changed partition, a seed that is not the committed digest's, or a
    seed case gone from the audit is refused before anything is written."""
    stage = h_stage.stage
    case = stage / "audit/cases" / _h_kept_case(h_stage)
    if defect == "edited_kept":
        verdict = _h_json(case / "verdict.json")
        verdict["rationale"] = "A rationale the judge never wrote."
        write_json(case / "verdict.json", verdict)
        _h_rebind_verdict(case)
    elif defect == "other_models":
        verdict = _h_json(case / "verdict.json")
        source = verdict["models"][0]["failure_source"]
        verdict["models"][0]["failure_source"] = (
            "llm_error" if source == "prompt_ambiguity" else "prompt_ambiguity"
        )
        write_json(case / "verdict.json", verdict)
        _h_rebind_verdict(case)
    elif defect == "unbound_sidecar":
        write_json(case / "verdict.meta.json", {"verdict_sha256": "0" * 64})
    elif defect == "edited_prompt":
        prompt = case / "prompt.md"
        prompt.write_text(prompt.read_text() + "One more fact.\n")
    elif defect == "forged_partition":
        changes = _h_json(stage / driver.PROMPT_CHANGES)
        changes["kept"].remove(case.name)
        changes["changed"].append(case.name)
        driver.write_json(stage / driver.PROMPT_CHANGES, changes)
    elif defect == "other_seed":
        prepared = _h_json(stage / "stage.json")
        prepared["seed"][case.name]["verdict_sha256"] = "0" * 64
        driver.write_json(stage / "stage.json", prepared)
    else:
        manifest = (stage / "audit/cases.jsonl").read_text().splitlines()
        kept = [line for line in manifest if case.name not in line]
        (stage / "audit/cases.jsonl").write_text("\n".join(kept) + "\n")
        shutil.rmtree(case)
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, message)


def test_a_manifest_claiming_the_new_model_on_a_kept_case_is_refused(h_stage):
    """cases.jsonl is editable: a kept case recorded as one the new model
    got wrong (every hash following) is refused, since on the MOCK board its
    staged prediction there is right."""
    stage = h_stage.stage
    case = stage / "audit/cases" / _h_kept_case(h_stage)
    manifest = [
        json.loads(line)
        for line in (stage / "audit/cases.jsonl").read_text().splitlines()
    ]
    for item in manifest:
        if item["case_id"] == case.name:
            item["wrong_models"].append(H_NEW)
    (stage / "audit/cases.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in manifest)
    )
    changes = _h_json(stage / driver.PROMPT_CHANGES)
    changes["kept"].remove(case.name)
    changes["changed"].append(case.name)
    driver.write_json(stage / driver.PROMPT_CHANGES, changes)
    prompt = case / "prompt.md"
    prompt.write_text(
        prompt.read_text() + "MOCK: one more wrong answer joined this case.\n"
    )
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, "wrong models disagree with the staged predictions")


def _h_annotations(h_stage) -> Path:
    return h_stage.stage / BUNDLE / "annotations"


def _h_edit_annotation(path: Path, case: str, column: str, value: str) -> str:
    import pandas as pd

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    _, scenario, variable = case.split("__")
    mask = (frame.scenario_id == scenario) & (frame.variable == variable)
    assert mask.sum() == 1
    old = frame.loc[mask, column].item()
    assert old != value
    frame.loc[mask, column] = value
    path.write_text(frame.to_csv(index=False))
    return old


def test_the_staged_annotations_are_triages_rebuilt_frames(h_stage):
    """The freeze's rebuild of the row annotations and case notes from the
    verdicts and the staged record (verify_annotation_amendments) gives the
    bytes the real triage wrote, every decided case's class applied, the
    ruled case's included."""
    import pandas as pd

    annotations = _h_annotations(h_stage)
    release.verify_annotation_amendments(
        annotations, [], h_stage.stage / "audit", driver.rejudged_cases(h_stage.stage)
    )
    notes = pd.read_csv(annotations / H_NOTES, dtype=str, keep_default_na=False)
    decided = _h_decided_cases()
    record = {
        driver.spec_key(entry): entry
        for entry in _h_json(annotations / driver.ADJUDICATIONS)["adjudications"]
    }
    assert len(notes) == len(decided) + 1 == len(record)
    for row in notes.itertuples():
        entry = record[(row.scenario_id, row.variable)]
        assert row.case_failure_sources == entry["adjudicated_failure_source"]


@pytest.mark.parametrize(
    "name, column",
    [
        (H_NOTES, "case_failure_sources"),
        (H_ROWS, "failure_source"),
        (H_NOTES, "reference_suspect"),
        (H_ROWS, "annotation"),
    ],
)
def test_the_freeze_refuses_an_annotation_no_judge_or_decision_gave(
    h_stage, name, column
):
    """On a kept decided case, a failure class, a flag or a diagnosis edited
    in the published annotations, with the receipt's hash following, is not
    what triage builds from the verdicts and the record."""
    case = _h_kept_case(h_stage)
    path = _h_annotations(h_stage) / name
    import pandas as pd

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    _, scenario, variable = case.split("__")
    old = frame.loc[
        (frame.scenario_id == scenario) & (frame.variable == variable), column
    ].item()
    value = {
        "case_failure_sources": "llm_error|prompt_ambiguity",
        "failure_source": (
            "reference_engine_defect"
            if old != "reference_engine_defect"
            else "llm_error"
        ),
        "reference_suspect": "False" if old == "True" else "True",
        "annotation": "A diagnosis no judge wrote.",
    }[column]
    _h_edit_annotation(path, case, column, value)
    h_stage.rebind(restamp=False)
    refused = _h_refused(
        h_stage, rf"Staged {re.escape(name)} is not what triage builds"
    )
    assert column in str(refused.value)


def test_the_freeze_refuses_a_case_note_without_its_adjudication_sentence(h_stage):
    """A decided case's note must carry its decision's exact sentence."""
    path = _h_annotations(h_stage) / H_NOTES
    _h_edit_annotation(path, _h_kept_case(h_stage), "case_annotation", "A note.")
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, f"Staged {re.escape(H_NOTES)} is not what triage builds")


def _h_record(h_stage) -> dict:
    return _h_json(_h_annotations(h_stage) / driver.ADJUDICATIONS)


def _h_write_record(h_stage, record: dict) -> None:
    (_h_annotations(h_stage) / driver.ADJUDICATIONS).write_text(
        driver.record_text(record)
    )


def _h_base_entry(record: dict, excluded: bool) -> dict:
    return next(
        e
        for e in record["adjudications"]
        if bool(e.get("excluded_from_scoring")) == excluded
        and driver.spec_key(e) != RULED
    )


def _h_ruled_entry(record: dict) -> dict:
    (entry,) = [e for e in record["adjudications"] if driver.spec_key(e) == RULED]
    return entry


H_CHANGED_DECISION = "change recorded decisions beyond the re-judged cases' judge"
H_RECORD_EDITS = {
    "dropped_decision": (
        lambda r: r["adjudications"].remove(_h_base_entry(r, excluded=False)),
        "drop recorded decisions",
    ),
    "adjudicated_class": (
        lambda r: _h_base_entry(r, excluded=False).update(
            adjudicated_failure_subtype="other"
        ),
        H_CHANGED_DECISION,
    ),
    "judge_class": (
        lambda r: _h_base_entry(r, excluded=True).update(judge_failure_subtype="other"),
        H_CHANGED_DECISION,
    ),
    "reasoning": (
        lambda r: _h_base_entry(r, excluded=False).update(
            reasoning="Reasoning nobody gave."
        ),
        H_CHANGED_DECISION,
    ),
    "ruled_reasoning": (
        lambda r: _h_ruled_entry(r).update(reasoning="Reasoning nobody gave."),
        "differs from the ruling's entry",
    ),
    "ruled_dropped": (
        lambda r: r["adjudications"].remove(_h_ruled_entry(r)),
        f"{H_RULED_CASE}: no staged decision",
    ),
    "note": (
        lambda r: r.update(note="Another note."),
        "changes its note, schema or date conventions",
    ),
    # The record's own parser refuses an ambiguous output left scored.
    "unexcluded": (
        lambda r: _h_base_entry(r, excluded=True).update(excluded_from_scoring=False),
        "requires excluded_from_scoring",
    ),
}


@pytest.mark.parametrize("edit", H_RECORD_EDITS)
def test_the_freeze_refuses_an_adjudication_record_the_release_does_not_give(
    h_stage, edit
):
    """The staged record is release 20261027's plus the ruling's entry: no
    base decision dropped, and no adjudicated or judge class, reasoning,
    note or exclusion changed (no case re-opened), and the ruled entry as the
    ruling gives it, each with the receipt's hash following."""
    from policybench.adjudications import AdjudicationError

    change, message = H_RECORD_EDITS[edit]
    record = _h_record(h_stage)
    change(record)
    _h_write_record(h_stage, record)
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, message, error=(SystemExit, AdjudicationError))


def test_a_record_whose_bytes_hide_text_is_refused(h_stage):
    """A duplicate key the parser drops, the receipt's hash following."""
    path = _h_annotations(h_stage) / driver.ADJUDICATIONS
    text = path.read_text()
    path.write_text(text.replace('"note":', '"note": "Hidden.", "note":', 1))
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, "is not in the committed form")


def test_a_changed_held_reference_record_is_refused(h_stage):
    path = h_stage.workspace / "reference_audit/held_references.json"
    path.write_bytes(path.read_bytes() + b" ")
    _h_refused(h_stage, "held_references.json changed from the base release")


def _h_edit_first_row(text: str, column: str, change) -> str:
    lines = text.splitlines(keepends=True)
    row = lines[1].split(",")
    assert row[0] == H_INCUMBENT
    at = H_COLUMNS.index(column)
    row[at] = change(row[at])
    return "".join([lines[0], ",".join(row), *lines[2:]])


@pytest.mark.parametrize("where", ["base", "stage"])
def test_an_incumbent_prediction_change_is_refused_before_mutation(h_stage, where):
    """The incumbent's rows are release 20261027's (MOCK baseline here),
    whether the change is in the baseline's rows or in the bundle's, every
    stage hash following."""

    def bump(value: str) -> str:
        return str(float(value) + 1)

    if where == "base":
        board = h_stage.board
        board.baseline = _h_edit_first_row(board.baseline, "prediction", bump)
    else:
        path = h_stage.stage / BUNDLE / "us/predictions.csv"
        path.write_text(_h_edit_first_row(path.read_text(), "prediction", bump))
        h_stage.rebind()
    _h_refused(h_stage, f"Incumbent prediction evidence changed: {H_INCUMBENT}$")


@pytest.mark.parametrize(
    "edit",
    [
        {"completed": 99},
        {"total": 99, "completed": 99},
        {"stopped_reason": "budget"},
        {"model": "gpt-6.1-sol"},
        {"treatment_fingerprint": None},
    ],
    ids=repr,
)
def test_an_incomplete_run_state_is_refused_before_mutation(h_stage, edit):
    """Claude Fable 5.2's pinned run itself incomplete, stopped, another
    model's or without its treatment, every pin and hash following it."""
    path = h_stage.stage / "inputs" / H_SLUG / "run_state.json"
    write_json(path, {**_h_json(path), **edit})
    h_stage.rebind(repin=True)
    _h_refused(h_stage, "Missing completed run or treatment evidence")


def test_a_run_state_treatment_off_the_registry_is_refused(h_stage):
    path = h_stage.stage / "inputs" / H_SLUG / "run_state.json"
    state = _h_json(path)
    state["treatment_fingerprint"]["request_timeout_seconds"] += 1
    write_json(path, state)
    h_stage.rebind(repin=True)
    _h_refused(h_stage, "disagrees with registry")


def _h_edit_rows(path: Path, model: str, column: str, value: str) -> None:
    import pandas as pd

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.loc[frame["model"] == model, column] = value
    path.write_text(frame.to_csv(index=False))


def test_an_answer_timed_before_the_response_window_is_refused(h_stage):
    """A request the run records before the configured response start, every
    pin and hash following, stops the freeze before it writes the pointer."""
    for path in (
        h_stage.stage / "inputs" / H_SLUG / "predictions.csv",
        h_stage.stage / BUNDLE / "us/predictions.csv",
    ):
        _h_edit_rows(path, H_NEW, "request_started_at", "1780000000.0")
    h_stage.rebind(repin=True)
    _h_refused(h_stage, "before the configured model response start")


@pytest.mark.parametrize(
    "defect, message",
    [
        ("stale_stage_json", "staged input changed since prepare: publish/"),
        ("unrecorded_input", "stage.json does not record"),
        ("provenance_hash", "model-provenance.json disagrees with the staged run"),
        ("fingerprint", "model-provenance.json disagrees with the staged run"),
    ],
)
def test_the_freeze_rechecks_the_prepare_time_hashes(h_stage, defect, message):
    """stage.json and model-provenance.json, both bound by the receipt, must
    still describe the staged inputs."""
    stage = h_stage.stage
    if defect == "stale_stage_json":
        path = stage / BUNDLE / "us/predictions.csv"
        path.write_text(path.read_text() + path.read_text().splitlines()[1] + "\n")
    elif defect == "unrecorded_input":
        prepared = _h_json(stage / "stage.json")
        del prepared["files"][f"inputs/{H_SLUG}/predictions.csv"]
        driver.write_json(stage / "stage.json", prepared)
    else:
        record = _h_json(stage / "model-provenance.json")
        if defect == "provenance_hash":
            record[H_NEW]["predictions_sha256"] = "0" * 64
        else:
            record[H_NEW]["treatment_fingerprint"]["request_timeout_seconds"] += 1
        driver.write_json(stage / "model-provenance.json", record)
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, message)


@pytest.mark.parametrize(
    "column, value",
    [("estimated_cost_usd", "0.0002"), ("elapsed_seconds", "9.5"), ("prediction", "1")],
)
def test_new_model_rows_edited_in_the_bundle_are_refused(h_stage, column, value):
    """The new model's cost, latency or answers edited in the bundle's
    predictions, with stage.json and model-provenance.json following, are not
    its pinned run's rows, column by column (verify_new_model_inputs)."""
    _h_edit_rows(h_stage.stage / BUNDLE / "us/predictions.csv", H_NEW, column, value)
    h_stage.rebind()
    refused = _h_refused(
        h_stage, "rows in the bundle's predictions are not the pinned run's"
    )
    assert column in str(refused.value)


def test_a_new_model_run_file_edited_with_the_bundle_is_refused(h_stage):
    """The run file and the bundle edited together, every stage hash
    following, are not the run file the committed pins name."""
    for path in (
        h_stage.stage / "inputs" / H_SLUG / "predictions.csv",
        h_stage.stage / BUNDLE / "us/predictions.csv",
    ):
        _h_edit_rows(path, H_NEW, "estimated_cost_usd", "0.0002")
    h_stage.rebind()
    _h_refused(h_stage, f"staged inputs/{H_SLUG}/predictions.csv is not the run file")


def test_input_pins_that_differ_from_their_commit_are_refused(h_stage):
    """The pins file edited in the working tree, not committed, is refused."""
    path = h_stage.workspace / driver.INPUT_PINS_PATH
    path.write_text(path.read_text().replace(H_RUN, "fable52-runs/other"))
    _h_refused(h_stage, "differs from its HEAD commit")


def test_input_pins_must_name_the_supervised_run(h_stage):
    """The frozen serving evidence names Claude Fable 5.2's supervised run from
    the committed pins, which must give it as <runs root>/fable52/run."""
    path = h_stage.workspace / driver.INPUT_PINS_PATH
    path.write_text(path.read_text().replace(f"{H_RUN}/run", "fable52-runs/run"))
    h_stage.board.committed[driver.INPUT_PINS_PATH] = path.read_bytes()
    _h_refused(h_stage, f"does not name the supervised run of {H_SLUG}")
