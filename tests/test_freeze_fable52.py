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


def real_spec() -> dict:
    return json.loads((REPO / driver.SPEC_PATH).read_text())


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
