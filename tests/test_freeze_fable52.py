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
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

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


def test_a_reworded_description_stops_the_count():
    versions = base_versions()
    live(versions)["description"] = live(versions)["description"].replace(
        "keep the values they were decided on", "keep their decided values"
    )
    with pytest.raises(SystemExit, match="changed form"):
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
        if path in release.MANIFEST_PINNED
        or not any(path[: len(prefix)] == prefix for prefix in release.MANIFEST_CHANGES)
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
        stage=stage, receipt=receipt, calls=[], changed=[], publication=[]
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
# MOCK, each set where named: Claude Fable 5.2's run (an answer for every one
# of the 1,984 outputs, each the reference but the ruled output's, timed
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
# MOCK: Claude Fable 5.2's first request, 2026-11-08 10:00 UTC; its rows are
# timed from here, so the response window ends that day.
H_ANSWERED = 1794132000.0
H_WINDOW = f"{freezer.MODEL_RESPONSE_START} to 2026-11-08"
H_JUDGED_AT = "2026-11-09T12:00:00+00:00"
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


def _h_country(stats: list[dict], records: list[dict], ruled: dict | None) -> dict:
    """A board the real dashboard validator accepts, wrong answers annotated:
    one unruled output, and the ruled output with a cell for every model,
    scored unless ``ruled`` (the d2180 record) excludes it."""
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
        if model == H_NEW:
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


def _h_boards() -> SimpleNamespace:
    """MOCK release 20261027's payload and the exporters' boards: synthetic
    modelStats for the real incumbent roster and Claude Fable 5.2, on the
    base's record (the scope export) and the release's (export_full_run)."""
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
    return SimpleNamespace(
        live={"countries": {"us": {"modelStats": live_stats}}},
        exports={
            "release": {"countries": {"us": _h_country(released, records, ruled)}},
            "scope": {
                "countries": {
                    "us": _h_country(copy.deepcopy([*live_stats, new]), base, None)
                }
            },
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

    mp.setattr(driver, "base_commit_blob", base_blob)
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
        return copy.deepcopy(board.exports["release"])

    def export_payload(bundle, base, exclusions=None, **kwargs):
        assert exclusions is not None
        return copy.deepcopy(board.exports["scope"])

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


def _h_judge_ruled_case(audit: Path) -> None:
    """The ruled case Claude Fable 5.2 opened, judged by Opus 5.5 on v2: a
    MOCK verdict with its full sidecar and a clean transcript."""
    from policybench.judge_template import template_header

    case = audit / "cases" / H_RULED_CASE
    case.mkdir(parents=True)
    prompt = template_header(driver.JUDGE_TEMPLATE_VERSION) + (
        f"\nClassify the synthetic wrong answer on {H_RULED_CASE}.\n"
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
    # MOCK: Claude Fable 5.2 right on every output but the ruled one; the
    # incumbent wrong on every decided case.
    with (us / driver.CSV_NAME).open(newline="") as stream:
        reference = list(csv.DictReader(stream))
    decided = _h_decided_cases()
    new = []
    for index, row in enumerate(reference):
        started = H_ANSWERED + index * 0.5
        value = row["value"]
        if (row["scenario_id"], row["variable"]) == RULED:
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
    for row in reference:
        if f"us__{row['scenario_id']}__{row['variable']}" in decided:
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
    seed = driver.seed_digest(audit)
    board.seed_sha256 = hashlib.sha256(
        driver.seed_digest_text(seed).encode()
    ).hexdigest()
    # The ruled case, which only Claude Fable 5.2 answered wrong: added.
    _h_judge_ruled_case(audit)
    manifest.append(
        {
            "case_id": H_RULED_CASE,
            "scenario_id": RULED[0],
            "variable": RULED[1],
            "wrong_models": [H_NEW],
            "parse_failure_only": False,
        }
    )
    manifest.sort(key=lambda item: item["case_id"])
    (audit / "cases.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in manifest)
    )
    driver.write_json(
        stage / driver.PROMPT_CHANGES,
        {"kept": sorted(seed), "changed": [], "added": [H_RULED_CASE]},
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


@pytest.fixture(scope="module")
def h_template(tmp_path_factory):
    """The releasable stage, built once: install-exclusions' record, the real
    adjudicate-exclusions, triage, write_judge_provenance and export (section
    comment)."""
    boards = _h_boards()
    board = SimpleNamespace(
        live=boards.live,
        exports=boards.exports,
        committed={},
        seed_sha256=None,
        baseline=None,
        reads=[],
        calls=[],
        defects=set(),
    )
    workspace = tmp_path_factory.mktemp("h-template") / "workspace"
    workspace.mkdir()
    with pytest.MonkeyPatch.context() as mp:
        _h_patch(mp, workspace, board)
        _h_write_checkout(workspace)
        stage = _h_write_stage(workspace, board)
        mp.setattr(driver, "SEED_DIGEST_SHA256", board.seed_sha256)
        args = SimpleNamespace(stage_dir=stage, partial=False, early=False)
        driver.adjudicate_exclusions(args)
        driver.triage(args, stage / BUNDLE)
        driver.write_judge_provenance(args)
        driver.export(args, stage / BUNDLE, copy.deepcopy(board.live))
        # The driver reads its committed inputs from REPO while the writable
        # checkout lives here. Bind the actual freeze inputs here.
        receipt_path = stage / "release-ready.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["repository_inputs"] = driver.repository_input_hashes(workspace)
        driver.write_json(receipt_path, receipt)
    board.reads.clear()
    return SimpleNamespace(workspace=workspace, board=board)


@pytest.fixture
def h_stage(h_template, tmp_path, monkeypatch):
    """A copy of the releasable stage and its checkout, the driver, the freeze
    and the freezer pointed at it."""
    workspace = tmp_path / "workspace"
    shutil.copytree(h_template.workspace, workspace)
    board = copy.deepcopy(h_template.board)
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
