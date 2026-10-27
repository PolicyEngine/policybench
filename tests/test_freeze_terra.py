"""Terra's freezer retains Argon's evidence gates and requires the 10-22 build.

Every writable input is synthetic and lives in pytest's temporary directory.
Committed reference files are read as fixtures; the real freezer never runs.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import finish_terra as driver  # noqa: E402
import freeze_snapshot as freezer  # noqa: E402
import freeze_terra as release  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
AUDIT = REPO / "reference_audit/2026-10-22-engine-upgrade"
BUILD = AUDIT / "reference-build"
RUN = driver.RUN_NAME
FROZEN = Path("paper/snapshot/20260501/runs") / RUN
BUNDLE = Path("publish") / RUN
EXPLANATIONS = "us_case_reference_explanations.csv"


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(autouse=True)
def no_real_freezer(monkeypatch):
    """A test reaching the actual snapshot writer fails before it writes."""
    import pandas as pd

    def refuse():
        raise AssertionError("A test reached the real freeze_snapshot.main")

    monkeypatch.setattr(freezer, "main", refuse)
    try:
        saved = pd.get_option("future.infer_string")
    except (KeyError, pd.errors.OptionError):
        saved = None
    yield
    if saved is not None:
        pd.set_option("future.infer_string", saved)


@pytest.fixture
def upgrade():
    """The real revision, with a synthetic narrative for independent gates."""
    meta = json.loads((BUILD / driver.META_NAME).read_text())
    revision = meta["revisions"][-1]
    return driver.Upgrade(
        engine_version=revision["engine_version"],
        previous_engine_version=driver.BASE_ENGINE,
        revision=revision,
        changed={
            driver.spec_key(item): item["regenerated"] for item in revision["changed"]
        },
        regenerated_base=frozenset(),
        regenerated_ruled=frozenset(),
        added=frozenset(),
        records=49,
        exclusions_text=(BUILD / "reference_exclusions.json").read_text(),
        sha256={
            **{name: sha(BUILD / name) for name in driver.BUILT_FILES},
            EXPLANATIONS: hashlib.sha256(b"synthetic narrative\n").hexdigest(),
            driver.ACTIONS_NAME: sha(AUDIT / driver.ACTIONS_NAME),
        },
    )


def engine_pins(workspace, version="2.60.0"):
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


@pytest.fixture
def installed(tmp_path, monkeypatch, upgrade):
    """An installed record whose build-loader gate is isolated in driver tests."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(release, "ROOT", workspace)
    engine_pins(workspace)
    stage = workspace / "stage"
    retained = stage / driver.BUILD_COPY
    retained.mkdir(parents=True)
    for name in driver.BUILT_FILES:
        shutil.copyfile(BUILD / name, retained / name)
    shutil.copyfile(AUDIT / driver.ACTIONS_NAME, retained / driver.ACTIONS_NAME)
    (retained / EXPLANATIONS).write_bytes(b"synthetic narrative\n")
    scoring = stage / "scoring"
    scoring.mkdir()
    for name in ("scenarios.csv", "scenarios.csv.meta.json"):
        (scoring / name).write_bytes(driver.base_commit_blob(FROZEN / name))
    prepared = {
        "early": False,
        "partial": False,
        "references_installed": driver.references_record(upgrade, None),
    }
    write_json(stage / "stage.json", prepared)
    receipt = {
        "files": {
            str(Path(driver.BUILD_COPY) / name): upgrade.sha256[name]
            for name in driver.BUILD_COPY_FILES
        }
    }
    monkeypatch.setattr(driver, "stage_upgrade", lambda stage: upgrade)
    monkeypatch.setattr(driver, "verify_recorded_drops", lambda *args: None)
    return SimpleNamespace(
        stage=stage,
        workspace=workspace,
        receipt=receipt,
        prepared=prepared,
        upgrade=upgrade,
    )


def test_the_freeze_adds_terra_under_the_driver_tag():
    assert release.NEW_MODELS == driver.MODELS == {"terra": "gpt-6.1-terra"}
    assert release.BOARD_MODELS == 51
    assert (driver.RELEASE_EXCLUSIONS, driver.RELEASE_SCORED) == (49, 1935)


@pytest.mark.parametrize("installed", [None, False, {}, "unbound"])
def test_the_freeze_requires_an_installed_build(tmp_path, installed):
    (tmp_path / "stage.json").write_text(
        json.dumps(
            {"early": False, "partial": False, "references_installed": installed}
        )
    )
    with pytest.raises(SystemExit, match="installed build"):
        release.verify_upgrade(tmp_path, {"files": {}})


# What a rehearsal stage.json may carry in place of each flag's False.
REHEARSAL_FLAGS = [True, "missing", None, 0, 1, "false", "False", [], {}]


@pytest.mark.parametrize("field", ["early", "partial"])
@pytest.mark.parametrize("value", REHEARSAL_FLAGS, ids=repr)
def test_the_freeze_refuses_a_rehearsal_stage(installed, field, value):
    """Review r1, finding 3: stage.json's early and partial flags must each be
    recorded as False. A flag that is True, missing or not a boolean stops the
    freeze, however valid the rest of the stage and its receipt."""
    assert release.verify_upgrade(installed.stage, installed.receipt)
    prepared = copy.deepcopy(installed.prepared)
    if value == "missing":
        del prepared[field]
    else:
        prepared[field] = value
    write_json(installed.stage / "stage.json", prepared)
    with pytest.raises(SystemExit, match="early/partial stage cannot become a release"):
        release.verify_upgrade(installed.stage, installed.receipt)


@pytest.mark.parametrize("prepared", [[], "stage", None, 0])
def test_the_freeze_refuses_a_stage_json_that_is_not_an_object(tmp_path, prepared):
    (tmp_path / "stage.json").write_text(json.dumps(prepared))
    with pytest.raises(SystemExit, match="early/partial stage cannot become a release"):
        release.verify_upgrade(tmp_path, {"files": {}})


def test_the_freeze_regates_the_installed_build(installed):
    assert (
        release.verify_upgrade(installed.stage, installed.receipt) == installed.upgrade
    )


def test_the_freeze_refuses_a_pyproject_pin_disagreeing_with_the_installed_engine(
    installed,
):
    path = installed.workspace / "pyproject.toml"
    path.write_text(path.read_text().replace("2.60.0", "2.41.0"))
    with pytest.raises(SystemExit, match="pin|engine|policyengine-us"):
        release.verify_upgrade(installed.stage, installed.receipt)


@pytest.mark.parametrize("target", ["package", "requires-dist"])
def test_the_freeze_refuses_a_lock_disagreeing_with_the_installed_engine(
    installed, target
):
    path = installed.workspace / "uv.lock"
    old = 'version = "2.60.0"' if target == "package" else 'specifier = "==2.60.0"'
    path.write_text(path.read_text().replace(old, old.replace("2.60.0", "2.41.0")))
    with pytest.raises(SystemExit, match="pin|engine|policyengine-us|uv.lock"):
        release.verify_upgrade(installed.stage, installed.receipt)


@pytest.mark.parametrize("unbound", [True, False])
def test_the_freeze_binds_every_retained_build_file(installed, unbound):
    for name in driver.BUILD_COPY_FILES:
        receipt = copy.deepcopy(installed.receipt)
        bound = str(Path(driver.BUILD_COPY) / name)
        if unbound:
            del receipt["files"][bound]
        else:
            receipt["files"][bound] = "0" * 64
        with pytest.raises(SystemExit, match="does not bind the installed build"):
            release.verify_upgrade(installed.stage, receipt)


def test_the_freeze_rechecks_the_installed_record_and_scenario_pins(installed):
    for name in ("scenarios.csv", "scenarios.csv.meta.json"):
        path = installed.stage / "scoring" / name
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        with pytest.raises(SystemExit, match="Staged scoring"):
            release.verify_upgrade(installed.stage, installed.receipt)
        path.write_bytes(original)
    installed.prepared["references_installed"]["scored_outputs"] = 1934
    write_json(installed.stage / "stage.json", installed.prepared)
    with pytest.raises(SystemExit, match="installed build's record"):
        release.verify_upgrade(installed.stage, installed.receipt)


@pytest.fixture
def reference_tree(tmp_path, upgrade):
    stage = tmp_path / "stage"
    source = stage / BUNDLE / "us"
    frozen = tmp_path / FROZEN
    source.mkdir(parents=True)
    frozen.mkdir(parents=True)
    for name in driver.BASE_REFERENCE_SHA256:
        base = driver.base_commit_blob(FROZEN / name)
        (frozen / name).write_bytes(base)
        (source / name).write_bytes(
            (BUILD / name).read_bytes() if name in driver.UPGRADED_FILES else base
        )
    (frozen.parents[1] / "us_reference_outputs.csv").write_bytes(
        driver.base_commit_blob(FROZEN / driver.CSV_NAME)
    )
    manifest = json.loads(driver.base_commit_blob(release.SNAPSHOT / "manifest.json"))
    return SimpleNamespace(stage=stage, source=source, frozen=frozen, manifest=manifest)


def verify_reference_tree(tree, upgrade):
    release.verify_references(
        tree.source,
        tree.frozen,
        tree.manifest,
        upgrade.sha256["reference_exclusions.json"],
        upgrade,
    )


def test_the_upgrade_replaces_only_its_pinned_files_and_can_freeze_twice(
    reference_tree, upgrade
):
    tree = reference_tree
    verify_reference_tree(tree, upgrade)
    for name, pin in driver.upgraded_reference_pins(upgrade).items():
        shutil.copyfile(tree.source / name, tree.frozen / name)
        tree.manifest["source_run_artifacts"][RUN]["files"][name] = pin
    shutil.copyfile(
        tree.source / driver.CSV_NAME,
        tree.frozen.parents[1] / "us_reference_outputs.csv",
    )
    tree.manifest["committed_snapshot_artifacts"]["us_reference_outputs.csv"] = (
        upgrade.sha256[driver.CSV_NAME]
    )
    tree.manifest["audit_annotation_artifacts"]["files"][EXPLANATIONS] = upgrade.sha256[
        EXPLANATIONS
    ]
    verify_reference_tree(tree, upgrade)


@pytest.mark.parametrize("name", ["scenarios.csv", "reference_outputs.csv"])
def test_an_unexplained_reference_or_scenario_change_is_refused(
    reference_tree, upgrade, name
):
    path = reference_tree.source / name
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(SystemExit, match=f"Staged {name} changed"):
        verify_reference_tree(reference_tree, upgrade)


def test_narratives_are_the_retained_builds_exact_bytes(installed):
    annotations = installed.stage / BUNDLE / "annotations"
    annotations.mkdir(parents=True)
    retained = installed.stage / driver.BUILD_COPY / EXPLANATIONS
    path = annotations / EXPLANATIONS
    shutil.copyfile(retained, path)
    release.verify_explanations(annotations, installed.upgrade, stage=installed.stage)
    path.write_bytes(path.read_bytes() + b"unreviewed wording")
    with pytest.raises(SystemExit, match="file byte for byte"):
        release.verify_explanations(
            annotations, installed.upgrade, stage=installed.stage
        )


def test_the_real_builds_engine_setup_passes_the_inherited_convention_gates(
    tmp_path, upgrade
):
    previous_meta, previous_builders = (
        freezer.REFERENCE_META_SOURCE,
        freezer.UPGRADE_BUILDERS,
    )
    setup = release.reference_engine_setup(freezer, BUILD, upgrade)
    assert setup == {"convention_count": 9, "output_scope_adapter_count": 1}
    assert freezer.REFERENCE_META_SOURCE == previous_meta
    assert freezer.UPGRADE_BUILDERS == previous_builders


def test_extending_the_builder_note_keeps_the_fix_module_pin_gate(tmp_path, upgrade):
    meta = json.loads((BUILD / driver.META_NAME).read_text())
    meta["revisions"][-1]["fix_modules"][0]["sha256"] = "0" * 64
    write_json(tmp_path / driver.META_NAME, meta)
    previous_meta, previous_builders = (
        freezer.REFERENCE_META_SOURCE,
        freezer.UPGRADE_BUILDERS,
    )
    with pytest.raises(SystemExit, match="pins sha256"):
        release.reference_engine_setup(freezer, tmp_path, upgrade)
    assert freezer.REFERENCE_META_SOURCE == previous_meta
    assert freezer.UPGRADE_BUILDERS == previous_builders


def test_held_references_remain_the_base_records_at_their_decided_values():
    release.verify_held_references(BUILD)


@pytest.mark.parametrize("changed_record", [True, False])
def test_a_changed_held_record_or_reference_is_refused(
    tmp_path, monkeypatch, changed_record
):
    monkeypatch.setattr(release, "ROOT", tmp_path)
    record = Path("reference_audit/held_references.json")
    original = driver.base_commit_blob(record)
    path = tmp_path / record
    path.parent.mkdir(parents=True)
    path.write_bytes(original + b" " if changed_record else original)
    source = tmp_path / "us"
    source.mkdir()
    shutil.copyfile(BUILD / driver.CSV_NAME, source / driver.CSV_NAME)
    if changed_record:
        match = "held_references.json changed"
    else:
        (source / driver.CSV_NAME).write_text("scenario_id,variable,value\n")
        match = "Held reference changed"
    with pytest.raises(SystemExit, match=match):
        release.verify_held_references(source)


def test_every_model_still_scores_1935_outputs(upgrade):
    exclusions = json.loads(upgrade.exclusions_text)["exclusions"]
    country = {
        "referenceExclusions": [
            {"scenarioId": item["scenario_id"], "variable": item["variable"]}
            for item in exclusions
        ],
        "modelStats": [{"model": "gpt-6.1-terra", "n": 1935}],
    }
    release.verify_scored_outputs(country, exclusions, upgrade)
    country["modelStats"][0]["n"] = 1934
    with pytest.raises(SystemExit, match="1935 outputs"):
        release.verify_scored_outputs(country, exclusions, upgrade)


@settings(max_examples=50, deadline=None)
@given(count=st.integers(min_value=0, max_value=49))
def test_the_version_description_counts_rechecks_and_is_idempotent(count):
    meta = json.loads((BUILD / driver.META_NAME).read_text())
    upgrade = SimpleNamespace(
        engine_version="policyengine-us 2.60.0",
        revision={"excluded_outputs_rechecked": [None] * count},
    )
    versions = json.loads(driver.base_commit_blob(release.VERSIONS))
    exclusions = json.loads((BUILD / "reference_exclusions.json").read_text())[
        "exclusions"
    ]
    assert meta["policyengine_bundles"]["us"]["model_version"] == "2.60.0"
    result = release.release_versions(versions, exclusions, "2026-10-27", upgrade)
    live = next(row for row in result["versions"] if row["id"] == result["default"])
    assert live["description"].startswith(
        "Scored reference outputs from policyengine-us 2.60.0 ("
    )
    assert live["description"].endswith(" - 51 models")
    assert (f"the {count} that move on 2.60.0" in live["description"]) == bool(count)
    assert release.release_versions(result, exclusions, "2026-10-27", upgrade) == result


@pytest.mark.parametrize(
    "timestamp",
    [None, "2026-10-23", "2026-10-23T00:00:00", "2026-10-23T01:00:00+01:00"],
)
def test_the_manifest_refresh_requires_a_UTC_timestamp(installed, timestamp):
    path = installed.stage / driver.BUILD_COPY / driver.META_NAME
    meta = json.loads(path.read_text())
    meta["regenerated_at_utc"] = timestamp
    write_json(path, meta)
    with pytest.raises(SystemExit, match="ISO timestamp in UTC"):
        release.upgraded_reference_refresh(installed.stage, installed.upgrade)


def test_the_manifest_refresh_uses_the_installed_sidecars_provenance(installed):
    refresh = release.upgraded_reference_refresh(installed.stage, installed.upgrade)
    assert refresh["policyengine_us_version"] == "2.60.0"
    assert refresh["reference_csv_sha256"] == installed.upgrade.sha256[driver.CSV_NAME]
    assert refresh["date"] == "2026-10-23"


def manifest_leaves(value, path=()):
    if isinstance(value, dict) and value:
        for key, item in value.items():
            yield from manifest_leaves(item, (*path, key))
    elif isinstance(value, list) and value:
        for index, item in enumerate(value):
            yield from manifest_leaves(item, (*path, index))
    else:
        yield path


@settings(max_examples=75, deadline=None)
@given(picks=st.sets(st.integers(min_value=0, max_value=10**6), max_size=6))
def test_upgrade_manifest_permissions_are_exact_for_every_leaf(picks):
    before = json.loads(driver.base_commit_blob(release.SNAPSHOT / "manifest.json"))
    after = copy.deepcopy(before)
    leaves = tuple(manifest_leaves(before))
    changed = {leaves[pick % len(leaves)] for pick in picks}
    for path in changed:
        cursor = after
        for part in path[:-1]:
            cursor = cursor[part]
        cursor[path[-1]] = "changed"
    pinned = release.MANIFEST_PINNED - release.UPGRADE_MANIFEST_UNPINNED
    prefixes = release.MANIFEST_CHANGES + release.UPGRADE_MANIFEST_CHANGES
    expected = {
        path
        for path in changed
        if path in pinned
        or not any(path[: len(prefix)] == prefix for prefix in prefixes)
    }
    assert set(release.manifest_problems(before, after, SimpleNamespace())) == expected


def test_the_registered_treatment_is_checked_against_the_current_card(
    tmp_path, monkeypatch
):
    """Argon's treatment gate is still the common registry comparator."""
    captured = []

    def capture(fingerprint, expected, **kwargs):
        captured.append(expected)

    state = {"model": "gpt-6.1-terra", "treatment_fingerprint": {}}
    path = tmp_path / "run_state.json"
    scenarios = REPO / FROZEN / "scenarios.csv"
    with monkeypatch.context() as capture_patch:
        capture_patch.setattr(freezer, "_validate_treatment_fingerprint", capture)
        release.validate_treatment(freezer, state, path, scenarios)
    expected = captured[0]
    state["treatment_fingerprint"] = {"fingerprint_version": 3, **expected}
    release.validate_treatment(freezer, state, path, scenarios)
    state["treatment_fingerprint"]["request_timeout_seconds"] += 1
    with pytest.raises(SystemExit, match="disagrees with registry"):
        release.validate_treatment(freezer, state, path, scenarios)


@pytest.fixture
def receipt_stage(tmp_path):
    case = "us__scenario_031__snap"
    required = [BUNDLE / "us" / name for name in driver.REFERENCE_FILES]
    required += [
        BUNDLE / "us/predictions.csv",
        *[BUNDLE / "annotations" / name for name in driver.ANNOTATION_FILES],
        *[Path("inputs/terra") / name for name in driver.PINNED_INPUTS],
        Path("model-provenance.json"),
        Path(driver.PROMPT_CHANGES),
        Path("stage.json"),
        Path("audit/cases.jsonl"),
        Path("audit/schema.json"),
        *[
            Path("audit/cases") / case / name
            for name in (
                "verdict.json",
                "verdict.meta.json",
                "prompt.md",
                "claude.transcript.jsonl",
            )
        ],
    ]
    for name in required:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"bound evidence: {name}\n")
    (tmp_path / "audit/cases.jsonl").write_text(
        json.dumps({"case_id": case, "parse_failure_only": False}) + "\n"
    )
    payload = tmp_path / "data-board51.json"
    payload.write_text("{}")
    receipt = {
        "payload_sha256": sha(payload),
        "models": 51,
        "partial": False,
        "release_tag": driver.RELEASE_TAG,
        "base_tag": driver.BASE_TAG,
        "base_sha256": driver.BASE_SHA256,
        "files": {str(name): sha(tmp_path / name) for name in required},
    }
    write_json(tmp_path / "release-ready.json", receipt)
    return SimpleNamespace(stage=tmp_path, payload=payload, receipt=receipt)


def test_the_export_receipt_keeps_argons_transcript_and_input_bindings(receipt_stage):
    board = receipt_stage
    assert (
        release.verify_receipt(board.stage, board.payload, driver.RELEASE_TAG)
        == board.receipt
    )
    for name in board.receipt["files"]:
        changed = copy.deepcopy(board.receipt)
        del changed["files"][name]
        write_json(board.stage / "release-ready.json", changed)
        with pytest.raises(SystemExit, match="does not bind"):
            release.verify_receipt(board.stage, board.payload, driver.RELEASE_TAG)


def test_changed_bound_evidence_is_refused_before_the_freezer_can_run(receipt_stage):
    board = receipt_stage
    path = board.stage / "inputs/terra/run_state.json"
    path.write_bytes(path.read_bytes() + b"edited")
    with pytest.raises(SystemExit, match="Staged evidence changed since strict export"):
        release.verify_receipt(board.stage, board.payload, driver.RELEASE_TAG)


def test_verdict_validation_still_reads_the_bound_seed(tmp_path, monkeypatch):
    seed = {"kept": {"verdict_sha256": "seed pin"}}
    seen = []
    monkeypatch.setattr(driver, "load_seed", lambda stage: seed)

    def validate(audit, *, seed):
        seen.append((audit, seed))
        return ["us__scenario_031__snap"]

    monkeypatch.setattr(driver, "validate_verdicts", validate)
    with pytest.raises(SystemExit, match="1 staged verdicts fail validation"):
        release.verify_verdicts(tmp_path)
    assert seen == [(tmp_path / "audit", seed)]


def test_a_new_verdicts_provenance_is_checked_again_at_freeze(tmp_path, monkeypatch):
    provenance = tmp_path / "judge_provenance.json"
    provenance.write_text("bound provenance")
    monkeypatch.setattr(driver, "JUDGE_PROVENANCE", provenance)
    seen = []
    monkeypatch.setattr(
        driver, "verify_judge_provenance", lambda *args: seen.append(args)
    )
    receipt = {
        "judge_provenance": {
            "path": driver.JUDGE_PROVENANCE_PATH,
            "sha256": sha(provenance),
        }
    }
    rejudged = frozenset({"us__scenario_031__snap"})
    release.verify_judge_provenance(tmp_path, receipt, rejudged)
    assert seen == [(tmp_path / "audit/cases", rejudged, provenance)]
    provenance.write_text("unbound provenance")
    with pytest.raises(SystemExit, match="judge provenance record"):
        release.verify_judge_provenance(tmp_path, receipt, rejudged)


def test_freeze_rebuild_preserves_the_upgrade_scope_gate(
    receipt_stage, upgrade, monkeypatch
):
    board = receipt_stage
    live = {"countries": {"us": {"modelStats": []}}}
    seen = []

    def build(bundle, base, *, upgrade):
        seen.append((bundle, base, upgrade))
        return {"recomputed": True}

    monkeypatch.setattr(driver, "build_payload", build)
    rebuilt = driver.payload_text({"recomputed": True})
    board.payload.write_text(rebuilt)
    release.rebuild_payload(board.stage, board.receipt, board.payload, live, upgrade)
    assert len(seen) == 1
    assert seen[0][0] != board.stage / BUNDLE
    assert seen[0][1:] == (live, upgrade)
    board.payload.write_text(driver.payload_text({"recomputed": False}))
    with pytest.raises(SystemExit, match="is not what export builds"):
        release.rebuild_payload(
            board.stage, board.receipt, board.payload, live, upgrade
        )


def test_an_installed_build_allows_the_argon_triage_interface(upgrade):
    """The required upgrade must also accept the release's empty triage list."""
    assert driver.triage_items(upgrade, {"triage_adjudications": []}) == []


def test_a_future_triage_wave_preserves_every_base_wave(monkeypatch):
    spec = driver.load_spec()
    day = spec["snapshot_date"]
    spec.update(triage_decided_on=day, triage_adjudications_written_on=day)
    monkeypatch.setattr(driver, "load_spec", lambda: spec)
    wave = driver.DecisionWave(day, excludes=False, affirms=True, upgrade=False)
    before = driver.base_adjudication_record()["date_conventions"]
    after = driver.release_date_conventions(before, wave)
    assert f"2026-10-10, 2026-10-14 or {day})" in after
    assert after.count("The 2026-10-14 wave's decisions") == 1
    assert after.count(f"The {day} wave's decisions") == 1


@pytest.fixture
def preinstallation(tmp_path, monkeypatch):
    """Synthetic files for the install, bind-seed, prepare command sequence."""
    sources = tmp_path / "build-sources"
    sources.mkdir()
    for name in driver.BUILD_COPY_FILES:
        (sources / name).write_text(f"synthetic {name}\n")
    grounding = tmp_path / "grounding.csv"
    grounding.write_text("synthetic grounding\n")
    stage = tmp_path / "stage"
    upgrade = driver.Upgrade(
        engine_version="policyengine-us 2.60.0",
        previous_engine_version=driver.BASE_ENGINE,
        revision={},
        changed={},
        regenerated_base=frozenset(),
        regenerated_ruled=frozenset(),
        added=frozenset(),
        records=49,
        exclusions_text=(sources / "reference_exclusions.json").read_text(),
        sha256={name: sha(sources / name) for name in driver.BUILD_COPY_FILES},
    )
    args = SimpleNamespace(
        step="install-references",
        stage_dir=stage,
        built=sources,
        explanations=sources / EXPLANATIONS,
        actions=sources / driver.ACTIONS_NAME,
        grounding=grounding,
        audit_seed=tmp_path / "seed",
        base_predictions=tmp_path / "base.csv.gz",
        base_payload=tmp_path / "base.json",
        runs_root=tmp_path / "runs",
        partial=False,
        early=False,
    )
    seed = {"seed-case": {"prompt_sha256": "prompt", "verdict_sha256": "verdict"}}
    calls = []
    monkeypatch.setattr(driver, "GROUNDING_SHA256", sha(grounding))
    monkeypatch.setattr(driver, "load_build", lambda *args: upgrade)
    monkeypatch.setattr(
        driver, "verify_engine_pins", lambda *args, **kwargs: calls.append("pins")
    )
    monkeypatch.setattr(driver, "seed_digest", lambda path: seed)

    def verify_seed(actual):
        assert actual == seed

    monkeypatch.setattr(driver, "verify_seed", verify_seed)
    monkeypatch.setattr(driver, "validate_stage_path", lambda *args: None)
    return SimpleNamespace(
        args=args, stage=stage, upgrade=upgrade, seed=seed, calls=calls
    )


def test_install_then_bind_seed_then_prepare_preserves_the_binding(
    preinstallation, monkeypatch
):
    board = preinstallation
    driver.install_references(board.args)
    marker = board.stage / "reference-install.json"
    assert not (board.stage / "stage.json").exists()
    assert json.loads(marker.read_text())["sha256"] == board.upgrade.sha256
    board.args.step = "bind-seed"
    driver.bind_seed(board.args)
    assert json.loads(marker.read_text())["seed"] == board.seed
    # Repeating the install retains the already verified seed binding.
    driver.install_references(board.args)
    assert json.loads(marker.read_text())["seed"] == board.seed

    def fold(args, runs, base, reference):
        board.calls.append("fold")
        bundle = board.stage / BUNDLE
        for name in (*driver.REFERENCE_FILES, "predictions.csv"):
            path = bundle / "us" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"folded {name}\n")
        return bundle, {}

    def prepare(args, bundle):
        board.calls.append("audit")
        assert not (board.stage / "stage.json").exists()
        return board.seed

    def install(args):
        board.calls.append("install-audit")
        assert args.built == board.stage / driver.BUILD_COPY
        assert (
            json.loads((board.stage / "stage.json").read_text())["seed"] == board.seed
        )

    board.args.step = "prepare"
    monkeypatch.setattr(driver, "parse_args", lambda argv: board.args)
    monkeypatch.setattr(driver, "discover_new_models", lambda root: [])
    monkeypatch.setattr(driver, "resolve_base", lambda args: (None, None, {}))
    monkeypatch.setattr(driver, "prepare_inputs", fold)
    monkeypatch.setattr(driver, "prepare_cases", prepare)
    monkeypatch.setattr(driver, "install_references", install)
    driver.main([])
    assert board.calls == ["pins", "pins", "pins", "fold", "audit", "install-audit"]


@pytest.mark.parametrize("defect", ["missing", "sha256", "engine"])
def test_prepare_refuses_an_absent_or_different_preinstalled_build(
    preinstallation, monkeypatch, defect
):
    board = preinstallation
    if defect != "missing":
        driver.install_references(board.args)
        marker = board.stage / "reference-install.json"
        record = json.loads(marker.read_text())
        if defect == "sha256":
            record["sha256"][driver.CSV_NAME] = "0" * 64
        else:
            record["engine_version"] = "policyengine-us 2.41.0"
        write_json(marker, record)
    board.args.step = "prepare"
    monkeypatch.setattr(driver, "parse_args", lambda argv: board.args)

    def forbid(root):
        raise AssertionError("prepare reached the run before gating its build")

    monkeypatch.setattr(driver, "discover_new_models", forbid)
    with pytest.raises(SystemExit, match="committed build|preinstalled build differs"):
        driver.main([])
    assert not (board.stage / "stage.json").exists()


def test_early_prepare_uses_the_installed_build_and_retains_its_rehearsal_flag(
    preinstallation, monkeypatch
):
    board = preinstallation
    driver.install_references(board.args)
    board.args.step = "prepare"
    board.args.early = True

    def fold(args, runs, base, reference):
        bundle = board.stage / BUNDLE
        for directory in (bundle / "us", board.stage / "scoring"):
            directory.mkdir(parents=True, exist_ok=True)
            for name in (*driver.REFERENCE_FILES, "predictions.csv"):
                (directory / name).write_text(f"base {name}\n")
        annotations = bundle / "annotations"
        annotations.mkdir()
        (annotations / EXPLANATIONS).write_text("base narrative\n")
        return bundle, {}

    def audit(*args):
        raise AssertionError("early prepare reached the audit")

    exported = []

    def export(args, bundle, live):
        receipt = json.loads((board.stage / "stage.json").read_text())
        assert receipt["early"] is True
        assert receipt["references_installed"]["sha256"] == board.upgrade.sha256
        assert receipt["exclusions_installed"]["engine_version"] == (
            board.upgrade.engine_version
        )
        for name in driver.UPGRADED_FILES:
            pin = board.upgrade.sha256[name]
            assert sha(bundle / "us" / name) == pin
            assert sha(board.stage / "scoring" / name) == pin
        assert (
            sha(bundle / "annotations" / EXPLANATIONS)
            == (board.upgrade.sha256[EXPLANATIONS])
        )
        exported.append(receipt)
        return {}

    monkeypatch.setattr(driver, "parse_args", lambda argv: board.args)
    monkeypatch.setattr(driver, "discover_new_models", lambda root: [])
    monkeypatch.setattr(driver, "resolve_base", lambda args: (None, None, {}))
    monkeypatch.setattr(driver, "prepare_inputs", fold)
    monkeypatch.setattr(driver, "prepare_cases", audit)
    monkeypatch.setattr(driver, "export", export)
    driver.main([])
    assert len(exported) == 1
    final = json.loads((board.stage / "stage.json").read_text())
    assert final["early"] is True
    assert final["references_installed"] == exported[0]["references_installed"]
    assert final["exclusions_installed"] == exported[0]["exclusions_installed"]


def test_a_synthetic_installed_release_passes_the_freeze_dry_run(
    installed, monkeypatch, capsys
):
    """Exercise main's upgrade wiring while individual tests cover its edges."""
    import pandas as pd

    import policybench.adjudications
    import policybench.dashboard_schema

    board = installed
    source = board.stage / BUNDLE
    us = source / "us"
    annotations = source / "annotations"
    us.mkdir(parents=True)
    annotations.mkdir()
    snapshot = board.workspace / release.SNAPSHOT
    frozen = board.workspace / FROZEN
    frozen.mkdir(parents=True)
    for name in driver.REFERENCE_FILES:
        base = driver.base_commit_blob(FROZEN / name)
        (frozen / name).write_bytes(base)
        (us / name).write_bytes(
            (BUILD / name).read_bytes() if name in driver.UPGRADED_FILES else base
        )
    (snapshot / "us_reference_outputs.csv").write_bytes(
        driver.base_commit_blob(FROZEN / driver.CSV_NAME)
    )
    (snapshot / "manifest.json").write_bytes(
        driver.base_commit_blob(release.SNAPSHOT / "manifest.json")
    )
    for name in driver.ANNOTATION_FILES:
        (annotations / name).write_bytes(
            b"synthetic narrative\n"
            if name == EXPLANATIONS
            else driver.base_commit_blob(release.ANNOTATIONS / name)
        )
    held = Path("reference_audit/held_references.json")
    (board.workspace / held).parent.mkdir()
    (board.workspace / held).write_bytes(driver.base_commit_blob(held))
    serving = release.base_serving_config()
    stats = [
        {"model": model, "condition": "no_tools", "n": 1935}
        for model in [*serving["models"], "gpt-6.1-terra"]
    ]
    payload = {
        "countries": {
            "us": {
                "modelStats": stats,
                "referenceExclusions": [
                    {"scenarioId": item["scenario_id"], "variable": item["variable"]}
                    for item in json.loads(board.upgrade.exclusions_text)["exclusions"]
                ],
            }
        }
    }
    (board.stage / "data-board51.json").write_text(driver.payload_text(payload))
    frame = pd.DataFrame(
        [
            {
                "model": "gpt-6.1-terra",
                "scenario_id": "scenario_000",
                "variable": "snap",
                "prediction": 1200.0,
            }
        ]
    )
    for column in freezer.PREDICTION_EVIDENCE_COLUMNS:
        if column not in frame:
            frame[column] = ""
    frame.to_csv(us / "predictions.csv", index=False)
    inputs = board.stage / "inputs/terra"
    write_json(
        inputs / "run_state.json",
        {
            "model": "gpt-6.1-terra",
            "completed": 100,
            "total": 100,
            "stopped_reason": None,
            "treatment_fingerprint": {},
        },
    )
    board.prepared["files"] = {}
    driver.bind_build_exclusions(board.stage, board.prepared, board.upgrade)
    board.receipt["files"].update(board.prepared["files"])
    write_json(board.stage / "stage.json", board.prepared)
    versions = board.workspace / release.VERSIONS
    versions.parent.mkdir(parents=True)
    versions.write_bytes(driver.base_commit_blob(release.VERSIONS))
    for name in driver.BASE_REPOSITORY_INPUT_FILES:
        path = board.workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(driver.base_commit_blob(name))
    timing = board.workspace / driver.REPOSITORY_INPUT_FILES[2]
    timing.parent.mkdir(parents=True, exist_ok=True)
    timing.write_text("{}\n")
    board.receipt["repository_inputs"] = driver.repository_input_hashes(board.workspace)
    monkeypatch.setattr(release, "verify_freezer_destinations", lambda freezer: None)
    monkeypatch.setattr(release, "verify_receipt", lambda *args: board.receipt)
    monkeypatch.setattr(driver, "verify_new_model_inputs", lambda stage: None)
    monkeypatch.setattr(release, "evidence_runs", lambda: {"terra": "terra-runs/terra"})
    monkeypatch.setattr(
        policybench.dashboard_schema,
        "validate_dashboard_payload",
        lambda *args, **kwargs: [],
    )
    monkeypatch.setattr(driver, "base_payload_from_commit", lambda: {})
    monkeypatch.setattr(release, "rebuild_payload", lambda *args: None)
    monkeypatch.setattr(release, "verify_verdicts", lambda stage: None)
    monkeypatch.setattr(driver, "rejudged_cases", lambda stage: frozenset())
    monkeypatch.setattr(release, "verify_judge_provenance", lambda *args: None)
    monkeypatch.setattr(driver, "load_amendments", lambda *args: [])
    monkeypatch.setattr(release, "verify_annotation_amendments", lambda *args: None)
    monkeypatch.setattr(release, "base_prediction_rows", lambda: frame.iloc[:0])
    monkeypatch.setattr(release, "validate_treatment", lambda *args: None)
    monkeypatch.setattr(
        freezer, "_run_state_prediction_evidence", lambda *args: {"kind": "run_state"}
    )
    monkeypatch.setattr(
        freezer, "model_response_window", lambda *args: "2026-06-12 to 2026-10-26"
    )
    monkeypatch.setattr(
        policybench.adjudications, "verify_adjudications_applied", lambda *args: None
    )
    monkeypatch.setattr(
        freezer, "verify_adjudications_keep_judge_verdicts", lambda *args: None
    )
    before = {
        path.relative_to(board.workspace): path.read_bytes()
        for path in board.workspace.rglob("*")
        if path.is_file()
    }
    release.main(["--stage-dir", str(board.stage), "--dry-run"])
    assert before == {
        path.relative_to(board.workspace): path.read_bytes()
        for path in board.workspace.rglob("*")
        if path.is_file()
    }
    assert "51 models" in capsys.readouterr().out


@pytest.mark.parametrize(
    "field,value",
    [
        ("judge_model_requested", "claude-sonnet-5-5"),
        ("judged_at_utc", None),
        ("judge_runner", "scripts/run_audit_codex.sh"),
    ],
)
def test_the_freeze_refuses_a_reference_only_rejudgment_by_another_judge(
    tmp_path, monkeypatch, field, value
):
    """The freeze re-runs the driver's verdict gate: a case the installed
    build re-opened, with Terra right and an incumbent wrong, must still
    show this release's judge, runner and UTC timestamp."""
    from policybench.audit import AUDIT_OUTPUT_SCHEMA
    from policybench.judge_template import template_header

    audit = tmp_path / "audit"
    case = audit / "cases/us__scenario_031__snap"
    case.mkdir(parents=True)
    (case / "prompt.md").write_text(template_header(2) + "\nMoved reference.\n")
    write_json(audit / "schema.json", AUDIT_OUTPUT_SCHEMA)
    (audit / "cases.jsonl").write_text(
        json.dumps(
            {
                "case_id": case.name,
                "wrong_models": ["claude-fable-5"],
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
        "rationale": "Synthetic.",
        "models": [
            {
                "model": "claude-fable-5",
                "failure_source": "llm_error",
                "failure_subtype": "thresholds_rates",
                "diagnosis": "Synthetic.",
            }
        ],
    }
    write_json(case / "verdict.json", verdict)
    meta = {
        "verdict_sha256": sha(case / "verdict.json"),
        "prompt_sha256": sha(case / "prompt.md"),
        "judge_runner": driver.JUDGE_RUNNER,
        "judge_model_requested": driver.JUDGE_MODEL,
        "judge_model_reported": [driver.JUDGE_MODEL],
        "judged_at_utc": "2026-10-26T12:00:00+00:00",
        "judge_template_version": driver.JUDGE_TEMPLATE_VERSION,
        "judge_isolation": {"tools": "none (--tools '')"},
        "judge_auth": {"method": "oauth_token", "account": None, "org": None},
        "judge_effort": "xhigh",
        "judge_account_declared": next(iter(driver.PROVENANCE_GROUPS)),
    }
    seed = {case.name: {"prompt_sha256": "0" * 64, "verdict_sha256": "1" * 64}}
    monkeypatch.setattr(driver, "load_seed", lambda stage: seed)
    write_json(case / "verdict.meta.json", meta)
    events = [
        {"type": "user", "message": {"content": (case / "prompt.md").read_text()}},
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
    release.verify_verdicts(tmp_path)
    if value is None:
        del meta[field]
    else:
        meta[field] = value
    write_json(case / "verdict.meta.json", meta)
    with pytest.raises(SystemExit, match="1 staged verdicts fail validation"):
        release.verify_verdicts(tmp_path)


def test_baseline_prediction_loader_reads_synthetic_committed_blob(
    tmp_path, monkeypatch
):
    import gzip
    import subprocess

    root = tmp_path / "repo"
    path = root / FROZEN / "predictions.csv.gz"
    path.parent.mkdir(parents=True)
    path.write_bytes(
        gzip.compress(b"model,scenario_id,variable,prediction\nincumbent,s1,snap,1\n")
    )
    subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
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

    def commit(message):
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run([*git, "commit", "-qm", message], check=True)

    commit("synthetic baseline predictions")
    monkeypatch.setattr(driver, "ROOT", root)
    monkeypatch.setattr(driver, "BASE_COMMIT", "HEAD")
    monkeypatch.setattr(release, "SNAPSHOT", Path("paper/snapshot/20260501"))
    expected = [
        {"model": "incumbent", "scenario_id": "s1", "variable": "snap", "prediction": 1}
    ]
    assert release.base_prediction_rows().to_dict("records") == expected
    path.write_bytes(b"corrupted synthetic gzip")
    assert release.base_prediction_rows().to_dict("records") == expected
    commit("corrupted synthetic baseline predictions")
    with pytest.raises(gzip.BadGzipFile):
        release.base_prediction_rows()


@pytest.mark.parametrize(
    "name",
    [
        "pyproject.toml",
        "uv.lock",
        "reference_audit/2026-10-22-engine-upgrade/verification/sweep_timing.json",
        "paper/snapshot/20260501/manifest.json",
        "app/src/data.versions.json",
        "app/public/paper/policybench.pdf",
        "app/public/paper/web/index.html",
        "app/public/paper/web/style.css",
    ],
)
def test_repository_input_edits_after_export_are_refused_without_writes(h_stage, name):
    path = h_stage.workspace / name
    path.write_bytes(path.read_bytes() + b"\n")
    _h_refused(h_stage, "Repository inputs changed since strict export")


@pytest.mark.parametrize("name", [str(p) for p in driver.BASE_REPOSITORY_INPUT_FILES])
def test_scoring_repository_inputs_keep_the_base_bytes_even_if_rebound(h_stage, name):
    path = h_stage.workspace / name
    path.write_bytes(path.read_bytes() + b"\n")
    receipt_path = h_stage.stage / "release-ready.json"
    receipt = _h_json(receipt_path)
    receipt["repository_inputs"][name] = sha(path)
    driver.write_json(receipt_path, receipt)
    _h_refused(h_stage, "Repository input changed from the base release")


@pytest.mark.parametrize("field", ["sha256", "url"])
def test_historical_versions_cannot_change_even_if_rebound(h_stage, field):
    path = h_stage.workspace / release.VERSIONS
    versions = _h_json(path)
    historical = next(item for item in versions["versions"] if item["id"] == "1.0")
    historical["artifact"][field] = "synthetic altered historical artifact"
    driver.write_json(path, versions)
    receipt_path = h_stage.stage / "release-ready.json"
    receipt = _h_json(receipt_path)
    receipt["repository_inputs"][str(release.VERSIONS)] = sha(path)
    driver.write_json(receipt_path, receipt)
    _h_refused(h_stage, "Historical data.versions.json entries changed")


@pytest.mark.parametrize("change", ["add", "delete", "remove_web"])
def test_the_export_binds_the_complete_rendered_paper_inventory(h_stage, change):
    web = h_stage.workspace / "app/public/paper/web"
    if change == "add":
        (web / "added.js").write_text("synthetic additional paper asset\n")
    elif change == "delete":
        (web / "style.css").unlink()
    else:
        shutil.rmtree(web)
    _h_refused(h_stage, "Repository inputs changed since strict export")


def test_the_export_must_bind_repository_inputs(h_stage):
    path = h_stage.stage / "release-ready.json"
    receipt = _h_json(path)
    del receipt["repository_inputs"]
    driver.write_json(path, receipt)
    _h_refused(h_stage, "Strict export receipt does not bind repository inputs")


def test_the_freeze_preserves_export_hashes_when_binding_its_outputs(h_stage):
    path = h_stage.stage / "release-ready.json"
    original = _h_json(path)["repository_inputs"]
    h_stage.run()
    receipt = _h_json(path)
    assert receipt["repository_inputs"] == original
    assert receipt["repository_postfreeze"] == {
        str(name): sha(h_stage.workspace / name)
        for name in (release.SNAPSHOT / "manifest.json", release.VERSIONS)
    }


# --- The freeze of an installed-build stage, through the real gates -------------
#
# Review r1, finding 4. The stage below is written by the driver's own steps
# where they run offline, on the real committed build: references_record and
# bind_build_exclusions as install-references records them, seed_digest,
# triage (the real collect_audit, adjudication record and annotation writer),
# write_judge_provenance and export (its pins, inputs, provenance, roster,
# scope check and the real dashboard validator). release.main then runs every
# one of its gates on that stage, and the tests at the end of the section
# freeze it.
#
# MOCK, each set where named: Terra's run (an answer for every one of the
# build's 1,984 outputs, each the build's reference, timed 2026-10-24 UTC);
# an incumbent's wrong answers on the 63 cases release 20261014's record
# decides and on one undecided case, with seed verdicts classed as each
# decision records its judge; the seed digest those verdicts give, in place
# of the committed one; the input pins, as if committed at HEAD; release
# 20261014's payload (synthetic modelStats under the real 50-model roster);
# the boards export_full_run and release_20261006.export_payload return
# (both compute from a full board); the incumbent's base prediction rows; and
# freeze_snapshot.main with the serving and registry lookups it makes
# (_h_freezer_main writes what the freezer writes, from where the freeze
# configured it). None of these values is a board-run result.
# _h_rejudge extends this fixture with a fresh isolated verdict, optionally
# adding a developer triage decision through the real adjudication steps.

import csv  # noqa: E402
import functools  # noqa: E402
import io  # noqa: E402
import re  # noqa: E402

import release_20261006  # noqa: E402

H_TERRA = driver.MODELS["terra"]
H_SLUG = "terra"
H_INCUMBENT = "claude-fable-5"
H_STAGE = Path("results/local/terra-stage")
H_BOARD = f"data-board{release.BOARD_MODELS}.json"
H_RUN = "terra-runs/terra"
# MOCK: Terra's first request, 2026-10-24 10:00 UTC; its rows are timed from
# here, so the response window ends that day.
H_ANSWERED = 1792836000.0
H_WINDOW = f"{freezer.MODEL_RESPONSE_START} to 2026-10-24"
H_ROWS, H_NOTES = release.ANNOTATION_CSVS
H_AMENDMENTS = release.COMMITTED_AMENDMENTS
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
    "UPGRADE_BUILDERS",
    "PUBLISHED_DASHBOARD_SOURCE",
    "PUBLISHED_DASHBOARD_ARTIFACT",
    "RUN_STATE_EVIDENCE",
    "AUDIT_CASES_DIR",
    "audit_judge_provenance",
    "developer_adjudications_block",
    "freeze_serving_configuration",
)
# MOCK usage for the incumbent whose usage export carries from the base.
H_FABLE_USAGE = {
    "costUsd": 12.5,
    "costPerHousehold": 0.125,
    "totalTokens": 1000000,
    "latencySeconds": 30.25,
}


@functools.cache
def _h_blob(path: str) -> bytes:
    """A file of release 20261014's tree (BASE_COMMIT), read once."""
    return driver.base_commit_blob(Path(path))


def h_blob(path) -> bytes:
    return _h_blob(Path(path).as_posix())


@functools.cache
def _h_fingerprint() -> str:
    """The treatment the registry gives Terra (validate_treatment's expected),
    as Terra's run state records it."""
    captured = []

    def capture(fingerprint, expected, **kwargs):
        captured.append(expected)

    original = freezer._validate_treatment_fingerprint
    freezer._validate_treatment_fingerprint = capture
    try:
        release.validate_treatment(
            freezer,
            {"model": H_TERRA, "treatment_fingerprint": {}},
            Path("run_state.json"),
            REPO / FROZEN / "scenarios.csv",
        )
    finally:
        freezer._validate_treatment_fingerprint = original
    return json.dumps({"fingerprint_version": 3, **captured[0]})


def h_fingerprint() -> dict:
    return json.loads(_h_fingerprint())


def _h_stat(model: str, exact: float, **usage) -> dict:
    return {
        "model": model,
        "condition": "no_tools",
        "score": exact,
        "exact": exact,
        "n": driver.RELEASE_SCORED,
        **usage,
    }


def _h_country(stats: list[dict], exclusions: list[dict]) -> dict:
    """A board the real dashboard validator accepts, wrong answers annotated."""
    return {
        "country": "us",
        "scenarios": {
            "scenario_000": {
                "country": "us",
                "state": "CA",
                "numAdults": 1,
                "numChildren": 0,
            }
        },
        "modelStats": stats,
        "programStats": [{"variable": "snap", "score": 50.0}],
        "heatmap": [],
        "scenarioPredictions": {
            "scenario_000": {
                "snap": {
                    H_INCUMBENT: {
                        "prediction": 900.0,
                        "groundTruth": 1200.0,
                        "thresholdScore": 0.0,
                        "failureSource": "llm_error",
                        "failureSubtype": "thresholds_rates",
                    },
                    H_TERRA: {
                        "prediction": 1200.0,
                        "groundTruth": 1200.0,
                        "thresholdScore": 100.0,
                    },
                }
            }
        },
        "failureModes": {"programs": [], "households": []},
        "referenceExclusions": [
            {"scenarioId": item["scenario_id"], "variable": item["variable"]}
            for item in exclusions
        ],
    }


def _h_boards(upgrade) -> SimpleNamespace:
    """MOCK release 20261014's payload and the exporters' boards: synthetic
    modelStats for the real incumbent roster, and for Terra."""
    incumbents = sorted(release.base_serving_config()["models"])
    live_stats = [
        _h_stat(model, 40.0 + index * 0.5, costUsd=1.25)
        for index, model in enumerate(incumbents)
        if model != H_INCUMBENT
    ]
    live_stats.append(_h_stat(H_INCUMBENT, 47.5, **H_FABLE_USAGE))
    terra = _h_stat(H_TERRA, 45.25, costUsd=0.5)
    base = json.loads(h_blob(FROZEN / "reference_exclusions.json"))["exclusions"]
    build = json.loads(upgrade.exclusions_text)["exclusions"]
    # export_full_run reports none of the carried usage: the incumbent's rows
    # record none of it.
    uncarried = copy.deepcopy(live_stats)
    for key in driver.CARRIED_USAGE[H_INCUMBENT]:
        del uncarried[-1][key]
    return SimpleNamespace(
        live={"countries": {"us": {"modelStats": live_stats}}},
        exports={
            "release": {"countries": {"us": _h_country([*uncarried, terra], build)}},
            "scope": {
                "countries": {
                    "us": _h_country(copy.deepcopy([*live_stats, terra]), base)
                }
            },
            "allowed": {
                "countries": {
                    "us": _h_country(copy.deepcopy([*live_stats, terra]), build)
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


def _h_serving_from_the_registry(board):
    """What freeze_serving_configuration writes in a checkout without the
    historical run directories: every incumbent registry-backed, and Terra
    backed by its run state (or, with the ``terra_registry`` defect, not)."""

    def freeze(destination: Path) -> None:
        base = json.loads(h_blob(release.SNAPSHOT / "model_serving_config.json"))
        serving = copy.deepcopy(base)
        for row in serving["models"].values():
            row["evidence"] = {"kind": "registry"}
        kind = "registry" if "terra_registry" in board.defects else "run_state"
        serving["models"][H_TERRA] = {
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
    ``board.defects`` applied, and records the configuration it found."""

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
        if "base_reference" in defects:
            (run / driver.CSV_NAME).write_bytes(h_blob(FROZEN / driver.CSV_NAME))
        (run / driver.META_NAME).write_bytes(freezer.REFERENCE_META_SOURCE.read_bytes())
        committed_csv = freezer.SNAPSHOT_DIR / "us_reference_outputs.csv"
        freezer.copy_exact(freezer.SOURCE_US / driver.CSV_NAME, committed_csv)
        if "base_csv_copy" in defects:
            committed_csv.write_bytes(h_blob(FROZEN / driver.CSV_NAME))
        if "other_exclusions" in defects:
            doc = json.loads((run / driver.EXCLUSIONS_NAME).read_text())
            doc["exclusions"][-2]["frozen_value"] += 1
            (run / driver.EXCLUSIONS_NAME).write_text(driver.exclusions_text(doc))
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
        manifest["scope"]["models"] = 50 if "models_50" in defects else 51
        manifest["model_response_date"] = (
            "2026-06-12 to 2026-10-23" if "window" in defects else window
        )
        records = json.loads((run / driver.EXCLUSIONS_NAME).read_text())["exclusions"]
        manifest["reference_exclusions"]["outputs"] = len(records)
        manifest["reference_exclusions"]["scored_outputs_per_model"] = 1984 - len(
            records
        )
        manifest["published_dashboard_artifact"] = freezer.PUBLISHED_DASHBOARD_ARTIFACT
        pointer = json.loads((freezer.ROOT / release.POINTER).read_text())
        manifest["live_dashboard_artifact"].update(
            {key: pointer[key] for key in ("tag", "asset", "url", "sha256", "bytes")}
        )
        files = manifest["source_run_artifacts"][RUN]["files"]
        files.update(freezer.REFERENCE_PINS)
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
        (freezer.SNAPSHOT_DIR / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )

    return main


def _h_patch(mp, workspace: Path, board) -> None:
    """Point the driver, the freeze and the freezer at ``workspace`` and at the
    MOCK sources the section's comment names."""
    import pandas as pd

    import policybench.full_run_export

    _h_point_freeze_at(workspace, mp)
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
        return copy.deepcopy(
            board.exports["allowed" if exclusions is None else "scope"]
        )

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


def _h_write_checkout(workspace: Path) -> None:
    """The checkout as release 20261014 left it, from git: its snapshot,
    annotations, pointer, version list and held-reference record; the
    dependencies pinned to the installed engine."""
    engine_pins(workspace)
    snapshot = workspace / release.SNAPSHOT
    names = [release.SNAPSHOT / name for name in ("manifest.json",)]
    names += [release.SNAPSHOT / "model_serving_config.json"]
    names += [FROZEN / name for name in driver.BASE_REFERENCE_SHA256]
    names += [
        release.ANNOTATIONS / name
        for name in (*driver.ANNOTATION_FILES, driver.ADJUDICATIONS, H_AMENDMENTS)
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


def _h_csv(rows) -> str:
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    for row in rows:
        writer.writerow(row)
    return stream.getvalue()


def _h_decided_cases() -> dict[str, dict]:
    """Release 20261014's decisions, by case id."""
    return {
        driver.case_id(entry): entry
        for entry in driver.base_adjudication_record()["adjudications"]
    }


def _h_verdict(source: str, subtype: str, suspect: bool) -> dict:
    return {
        "reference_suspect": suspect,
        "reference_bug_hypothesis": "",
        "case_failure_source": source,
        "case_failure_subtype": subtype,
        "rationale": "The model applied the rule this case turns on incorrectly.",
        "models": [
            {
                "model": H_INCUMBENT,
                "failure_source": source,
                "failure_subtype": subtype,
                "diagnosis": "The model applied an outdated threshold.",
            }
        ],
    }


def _h_write_stage(workspace: Path, board, build, upgrade) -> Path:
    """The stage prepare, install-references and bind-seed leave: release
    20261014's references, then the installed build's, in the scoring source
    and the bundle; the build verbatim; Terra's run and the bundle's
    predictions; the seed audit; stage.json, model-provenance.json and
    prompt-changes.json; and the input pins."""
    from policybench.audit import AUDIT_OUTPUT_SCHEMA
    from policybench.judge_template import template_header

    stage = workspace / H_STAGE
    bundle = stage / BUNDLE
    us, annotations = bundle / "us", bundle / "annotations"
    scoring, retained = stage / "scoring", stage / driver.BUILD_COPY
    for directory in (us, annotations, scoring, retained):
        directory.mkdir(parents=True)
    for target in (us, scoring):
        for name in driver.BASE_REFERENCE_SHA256:
            (target / name).write_bytes(h_blob(FROZEN / name))
    (annotations / driver.ADJUDICATIONS).write_bytes(
        h_blob(release.ANNOTATIONS / driver.ADJUDICATIONS)
    )
    for name in driver.BUILT_FILES:
        shutil.copyfile(build.built / name, retained / name)
    shutil.copyfile(build.explanations, retained / EXPLANATIONS)
    shutil.copyfile(build.actions, retained / driver.ACTIONS_NAME)
    for target in (us, scoring):
        for name in driver.UPGRADED_FILES:
            shutil.copyfile(build.built / name, target / name)
    shutil.copyfile(build.explanations, annotations / EXPLANATIONS)
    # MOCK: Terra right on every output of the build; the incumbent wrong on
    # every decided case and on one undecided case.
    with (us / driver.CSV_NAME).open(newline="") as stream:
        reference = list(csv.DictReader(stream))
    decided = _h_decided_cases()
    moved = {driver.output_case(key) for key in upgrade.changed}
    undecided = next(
        driver.output_case((row["scenario_id"], row["variable"]))
        for row in reference
        if row["variable"] == "free_school_meals_eligible"
        and float(row["value"]) == 1.0
        and driver.output_case((row["scenario_id"], row["variable"]))
        not in {*decided, *moved}
    )
    board.undecided = undecided
    terra = []
    for index, row in enumerate(reference):
        started = H_ANSWERED + index * 0.5
        terra.append(
            [
                H_TERRA,
                row["scenario_id"],
                row["variable"],
                row["value"],
                "Synthetic answer.",
                "{}",
                H_TERRA,
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
        if driver.output_case((row["scenario_id"], row["variable"])) in {
            *decided,
            undecided,
        }:
            prediction = float(row["value"]) + 1000.0
            wrong.append(
                [H_INCUMBENT, row["scenario_id"], row["variable"], prediction]
                + ["Synthetic wrong answer."]
                + [""] * (len(H_COLUMNS) - 5)
            )
    inputs = stage / "inputs" / H_SLUG
    inputs.mkdir(parents=True)
    (inputs / "predictions.csv").write_text(_h_csv([H_COLUMNS, *terra]))
    write_json(
        inputs / "run_state.json",
        {
            "model": H_TERRA,
            "total": 100,
            "completed": 100,
            "stopped_reason": None,
            "treatment_fingerprint": h_fingerprint(),
        },
    )
    (us / "predictions.csv").write_text(_h_csv([H_COLUMNS, *wrong, *terra]))
    board.baseline = _h_csv([H_COLUMNS, *wrong])
    # MOCK: the seed audit, one kept case per decided output and the
    # undecided one, each verdict classed as its decision records the judge.
    audit = stage / "audit"
    (audit / "cases").mkdir(parents=True)
    write_json(audit / "schema.json", AUDIT_OUTPUT_SCHEMA)
    manifest = []
    for case in sorted({*decided, undecided}):
        entry = decided.get(case)
        verdict = (
            _h_verdict(
                entry["judge_failure_source"],
                entry["judge_failure_subtype"],
                bool(entry.get("judge_reference_suspect")),
            )
            if entry
            else _h_verdict("llm_error", "thresholds_rates", False)
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
    (audit / "cases.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in manifest)
    )
    seed = driver.seed_digest(audit)
    board.seed_sha256 = hashlib.sha256(
        driver.seed_digest_text(seed).encode()
    ).hexdigest()
    driver.write_json(
        stage / driver.PROMPT_CHANGES,
        {"kept": sorted(seed), "changed": [], "added": []},
    )
    prepared = {
        "partial": False,
        "early": False,
        "base_tag": driver.BASE_TAG,
        "base_commit": driver.BASE_COMMIT,
        "files": {},
        "seed": seed,
        "references_installed": driver.references_record(upgrade, None),
        "adjudications_dropped": [],
    }
    driver.bind_build_exclusions(stage, prepared, upgrade)
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
            H_TERRA: {
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
    """The releasable stage, built once: install-references' records, the
    real triage, write_judge_provenance and export (section comment)."""
    built, explanations, actions = driver.committed_build_sources(
        tmp_path_factory.mktemp("h-build")
    )
    build = SimpleNamespace(built=built, explanations=explanations, actions=actions)
    upgrade = driver.load_build(built, explanations, actions)
    boards = _h_boards(upgrade)
    board = SimpleNamespace(
        live=boards.live,
        exports=boards.exports,
        committed={},
        seed_sha256=None,
        baseline=None,
        undecided=None,
        reads=[],
        calls=[],
        defects=set(),
    )
    workspace = tmp_path_factory.mktemp("h-template") / "workspace"
    workspace.mkdir()
    with pytest.MonkeyPatch.context() as mp:
        _h_patch(mp, workspace, board)
        _h_write_checkout(workspace)
        stage = _h_write_stage(workspace, board, build, upgrade)
        mp.setattr(driver, "SEED_DIGEST_SHA256", board.seed_sha256)
        args = SimpleNamespace(stage_dir=stage, partial=False, early=False)
        driver.triage(args, stage / BUNDLE)
        driver.write_judge_provenance(args)
        driver.export(args, stage / BUNDLE, copy.deepcopy(board.live))
        # The fixture's driver reads its committed build from REPO while its
        # writable checkout lives here. Bind the actual freeze inputs here.
        receipt_path = stage / "release-ready.json"
        receipt = json.loads(receipt_path.read_text())
        receipt["repository_inputs"] = driver.repository_input_hashes(workspace)
        driver.write_json(receipt_path, receipt)
    board.reads.clear()
    return SimpleNamespace(workspace=workspace, board=board, upgrade=upgrade)


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
        upgrade=h_template.upgrade,
        files=files,
        rebind=rebind,
        run=run,
    )


def _h_export(h_stage):
    """Export with the synthetic checkout's repository inputs bound."""
    stage = h_stage.stage
    args = SimpleNamespace(stage_dir=stage, partial=False, early=False)
    driver.export(args, stage / BUNDLE, copy.deepcopy(h_stage.board.live))
    receipt = _h_json(stage / "release-ready.json")
    receipt["repository_inputs"] = driver.repository_input_hashes(h_stage.workspace)
    driver.write_json(stage / "release-ready.json", receipt)


def _h_rejudge(h_stage, monkeypatch, *, new_case=False, adjudicated=True):
    """Add a fresh judgment, optionally affirming its reference through triage."""
    from policybench.judge_template import template_header

    stage = h_stage.stage
    case_id = h_stage.board.undecided
    _, scenario, variable = case_id.split("__")
    for path in (
        stage / "inputs" / H_SLUG / "predictions.csv",
        stage / BUNDLE / "us/predictions.csv",
    ):
        with path.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            if (row["model"], row["scenario_id"], row["variable"]) == (
                H_TERRA,
                scenario,
                variable,
            ):
                assert float(row["prediction"]) == 1.0
                row["prediction"] = "0"
        path.write_text(_h_csv([H_COLUMNS, *[list(row.values()) for row in rows]]))
    audit = stage / "audit"
    items = [
        json.loads(line) for line in (audit / "cases.jsonl").read_text().splitlines()
    ]
    for item in items:
        if item["case_id"] == case_id:
            item["wrong_models"] = sorted([H_INCUMBENT, H_TERRA])
    (audit / "cases.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in items)
    )
    changes = _h_json(stage / driver.PROMPT_CHANGES)
    changes["kept"].remove(case_id)
    changes["added" if new_case else "changed"].append(case_id)
    driver.write_json(stage / driver.PROMPT_CHANGES, changes)
    case = audit / "cases" / case_id
    prompt = template_header(driver.JUDGE_TEMPLATE_VERSION) + (
        f"\nClassify both synthetic wrong answers on {case_id}.\n"
    )
    (case / "prompt.md").write_text(prompt)
    verdict = _h_verdict("llm_error", "thresholds_rates", adjudicated)
    verdict["models"].append({**verdict["models"][0], "model": H_TERRA})
    driver.write_json(case / "verdict.json", verdict)
    driver.write_json(
        case / "verdict.meta.json",
        {
            "verdict_sha256": sha(case / "verdict.json"),
            "prompt_sha256": sha(case / "prompt.md"),
            "judge_template_version": driver.JUDGE_TEMPLATE_VERSION,
            "judge_model_requested": driver.JUDGE_MODEL,
            "judge_model_reported": [driver.JUDGE_MODEL],
            "judge_runner": driver.JUDGE_RUNNER,
            "judged_at_utc": "2026-10-24T12:00:00+00:00",
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
    spec = driver.load_spec()
    if adjudicated:
        spec.update(
            triage_decided_on="2026-10-24",
            triage_adjudications_written_on="2026-10-24",
            triage_adjudications=[
                {
                    "scenario_id": scenario,
                    "variable": variable,
                    "adjudicated_failure_source": "llm_error",
                    "adjudicated_failure_subtype": "thresholds_rates",
                    "adjudicated_on": "2026-10-24",
                    "reference_verdict": "affirmed",
                    "reference_basis": (
                        "The synthetic reference follows the stated rule."
                    ),
                    "reasoning": "The synthetic models used an outdated threshold.",
                }
            ],
        )
    spec_path = h_stage.workspace / "docs/terra/spec.json"
    driver.write_json(spec_path, spec)
    monkeypatch.setattr(driver, "SPEC_PATH", spec_path)
    prepared = _h_json(stage / "stage.json")
    if new_case:
        del prepared["seed"][case_id]
        board_seed = driver.seed_digest_text(prepared["seed"]).encode()
        h_stage.board.seed_sha256 = hashlib.sha256(board_seed).hexdigest()
        monkeypatch.setattr(driver, "SEED_DIGEST_SHA256", h_stage.board.seed_sha256)
    for key in ("references_installed", "exclusions_installed"):
        prepared[key]["spec_sha256"] = sha(spec_path)
    driver.write_json(stage / "stage.json", prepared)
    record = driver.exclusion_adjudications(
        driver.base_adjudication_record(),
        audit / "cases",
        triage=driver.triage_items(h_stage.upgrade),
    )
    (stage / BUNDLE / "annotations" / driver.ADJUDICATIONS).write_text(
        driver.record_text(record)
    )
    h_stage.rebind(repin=True)
    args = SimpleNamespace(stage_dir=stage, partial=False, early=False)
    driver.triage(args, stage / BUNDLE)
    driver.write_judge_provenance(args)
    _h_export(h_stage)
    return case_id


def test_rejudged_adjudicated_stage_passes_the_freeze(h_stage, monkeypatch):
    _h_rejudge(h_stage, monkeypatch)
    before = h_stage.files()
    h_stage.run("--dry-run")
    assert h_stage.files() == before


def test_rebound_numeric_explanation_reaches_run_state_evidence_gate(h_stage):
    """Text equality accepts '001'; the run-only pandas frame parses it as 1."""
    import pandas as pd

    stage = h_stage.stage
    for path in (
        stage / "inputs" / H_SLUG / "predictions.csv",
        stage / BUNDLE / "us/predictions.csv",
    ):
        with path.open(newline="") as stream:
            rows = list(csv.DictReader(stream))
        for row in rows:
            if row["model"] == H_TERRA:
                row["explanation"] = "001"
        path.write_text(_h_csv([H_COLUMNS, *[list(row.values()) for row in rows]]))
    h_stage.rebind(repin=True)
    assert driver.new_model_row_differences(stage) == []
    source = pd.read_csv(stage / "inputs" / H_SLUG / "predictions.csv")
    combined = pd.read_csv(stage / BUNDLE / "us/predictions.csv", low_memory=False)
    assert source.explanation.iloc[0] == 1
    assert set(combined.loc[combined.model == H_TERRA, "explanation"]) == {"001"}
    _h_refused(h_stage, "Run-state prediction evidence failed")


def test_rebound_adjudication_wording_reaches_applied_sentence_gate(
    h_stage, monkeypatch
):
    from policybench.adjudications import AdjudicationError, apply_adjudications
    from policybench.audit import collect_audit

    case_id = _h_rejudge(h_stage, monkeypatch)
    stage = h_stage.stage
    amendments = [
        {
            "case_id": case_id,
            "field": "case_annotation",
            "old": "Developer adjudication (",
            "new": "Developer review (",
            "reason": "A wording change",
        }
    ]
    driver.write_json(stage / driver.AMENDMENTS, {"amendments": amendments})
    audit = stage / "audit"
    annotations = stage / BUNDLE / "annotations"
    collected = collect_audit(stage / BUNDLE / "us", audit)
    cases = collected["case"].rename(
        columns={
            "case_failure_source": "case_failure_sources",
            "case_failure_subtype": "case_failure_subtypes",
        }
    )
    rows, cases, _ = apply_adjudications(
        collected["row"],
        cases,
        freezer.load_adjudications(annotations / driver.ADJUDICATIONS),
    )
    driver.amend_annotations(
        rows, cases, driver.load_amendments(stage, frozenset({case_id}))
    )
    for name, frame in ((H_ROWS, rows), (H_NOTES, cases)):
        (annotations / name).write_text(driver.annotation_csv_text(frame))
    _h_export(h_stage)
    h_stage.rebind()
    _h_refused(
        h_stage,
        "does not carry the recorded adjudication sentence",
        error=AdjudicationError,
    )


def test_rebound_nonisolated_verdict_is_refused_at_export_and_freeze(
    h_stage, monkeypatch
):
    case_id = _h_rejudge(h_stage, monkeypatch)
    stage = h_stage.stage
    case = stage / "audit/cases" / case_id
    meta = _h_json(case / "verdict.meta.json")
    meta.pop("judge_isolation")
    driver.write_json(case / "verdict.meta.json", meta)
    (case / "claude.transcript.jsonl").unlink()
    record = _h_json(driver.JUDGE_PROVENANCE)
    entry = next(item for item in record["verdicts"] if item["case_id"] == case_id)
    entry["isolated"] = False
    entry["group"] = entry["group"].removeprefix("isolated: ")
    record["counts"] = {entry["group"]: 1}
    record["note"] = driver.provenance_note(record["verdicts"])
    driver.write_json(driver.JUDGE_PROVENANCE, record)
    h_stage.rebind()
    before = h_stage.files()
    args = SimpleNamespace(stage_dir=stage, partial=False, early=False)
    with pytest.raises(SystemExit, match="isolation|isolated|account"):
        driver.export(args, stage / BUNDLE, copy.deepcopy(h_stage.board.live))
    assert h_stage.files() == before
    _h_refused(h_stage, "validation|isolation|isolated|account")


def _unlisted_verdict(stage):
    """A synthetic unbound sidecar the historical whole-tree tally accepts."""
    case = stage / "audit/cases/us__extra__invented"
    write_json(case / "verdict.json", {})
    write_json(
        case / "verdict.meta.json",
        {
            "verdict_sha256": sha(case / "verdict.json"),
            "judge_model_requested": "invented-judge",
            "judge_model_reported": ["invented-judge"],
            "judge_runner": "scripts/run_audit_claude.sh",
        },
    )
    return case


@pytest.mark.parametrize("operation", ["export", "freeze", "dry-run"])
def test_unlisted_verdict_added_after_export_is_refused_without_writes(
    h_stage, operation
):
    stage = h_stage.stage
    _unlisted_verdict(stage)
    before = h_stage.files()
    with pytest.raises(SystemExit, match="not manifest-listed judged cases"):
        if operation == "export":
            args = SimpleNamespace(stage_dir=stage, partial=False, early=False)
            driver.export(args, stage / BUNDLE, copy.deepcopy(h_stage.board.live))
        else:
            h_stage.run(*(["--dry-run"] if operation == "dry-run" else []))
    assert h_stage.files() == before
    assert h_stage.board.calls == []


def test_verdict_inventory_refuses_a_nested_directory_symlink(tmp_path):
    audit = tmp_path / "audit"
    audit.mkdir()
    (audit / "cases.jsonl").write_text("")
    external = tmp_path / "unlisted"
    write_json(external / "verdict.json", {})
    container = audit / "cases/container"
    container.mkdir(parents=True)
    (container / "linked").symlink_to(external, target_is_directory=True)
    before = {p: p.read_bytes() for p in audit.rglob("*") if p.is_file()}
    with pytest.raises(SystemExit, match="audit case directory symlinks"):
        driver.verify_verdict_inventory(audit)
    assert {p: p.read_bytes() for p in audit.rglob("*") if p.is_file()} == before


def test_the_terra_provenance_tally_reads_only_bound_manifest_cases(h_stage):
    stage = h_stage.stage
    # Carried-verdict fixtures elsewhere need only their seed hash. Supply
    # complete synthetic identity fields here to exercise the real tally.
    for sidecar in (stage / "audit/cases").glob("*/verdict.meta.json"):
        meta = _h_json(sidecar)
        meta.update(
            judge_model_requested="synthetic-carried-judge",
            judge_model_reported=["synthetic-carried-judge"],
            judge_runner="scripts/run_audit_claude.sh",
        )
        write_json(sidecar, meta)
    h_stage.rebind(restamp=False)
    receipt = release.verify_receipt(stage, stage / H_BOARD, driver.RELEASE_TAG)
    release.verify_verdicts(stage)
    case_ids = driver.verify_verdict_inventory(stage / "audit")
    for case_id in case_ids:
        assert f"audit/cases/{case_id}/verdict.json" in receipt["files"]
        assert f"audit/cases/{case_id}/verdict.meta.json" in receipt["files"]
    cases = stage / "audit/cases"
    expected = freezer.audit_judge_provenance(cases)
    assert freezer.audit_judge_provenance(cases, case_ids=case_ids) == expected
    _unlisted_verdict(stage)
    # Keep the shared freezer's historical default: prior releases still read
    # their whole audit tree. Terra supplies an explicit receipt-bound list.
    whole_tree = freezer.audit_judge_provenance(cases)
    assert whole_tree["cases_judged"] == expected["cases_judged"] + 1
    assert whole_tree["by_judge"]["invented-judge"]["cases"] == 1
    assert freezer.audit_judge_provenance(cases, case_ids=case_ids) == expected

    release.configure_freezer(
        freezer,
        snapshot_date="2026-10-27",
        source_run=stage / BUNDLE,
        payload_path=stage / H_BOARD,
        pointer={
            key: "synthetic" for key in ("tag", "asset", "url", "sha256", "bytes")
        },
        evidence_paths={},
        cases_dir=cases,
        judged_case_ids=case_ids,
        previous_serving={},
        incumbents=set(),
        runs={},
    )
    assert freezer.audit_judge_provenance() == expected


def test_the_releasable_stage_passes_every_gate_and_a_dry_run_writes_nothing(
    h_stage, capsys
):
    before = h_stage.files()
    h_stage.run("--dry-run")
    assert h_stage.files() == before
    assert h_stage.board.calls == []
    out = capsys.readouterr().out
    assert f"Validated local release inputs: {driver.RELEASE_TAG}, 51 models" in out
    assert "references upgraded to policyengine-us 2.60.0" in out
    assert "49 exclusions (0 new)" in out
    assert f"model responses {H_WINDOW}; snapshot 2026-10-27; nothing written" in out


def _h_json(path: Path) -> dict:
    return json.loads(path.read_text())


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
    """The pointer and version list, the frozen run's build references and
    exclusion record, the committed copy of the reference outputs, the
    annotations (the staged record and CSVs, the build's narratives and
    release 20261014's amendments record), the serving rows, the manifest's
    statements, and the predictions asset and cache."""
    stage, root, upgrade = h_stage.stage, h_stage.workspace, h_stage.upgrade
    payload = stage / H_BOARD
    h_stage.run()
    assert f"Built {driver.RELEASE_TAG} locally" in capsys.readouterr().out
    pointer = _h_pointer(stage)
    assert (root / release.POINTER).read_text() == (
        json.dumps(pointer, indent=2, sort_keys=True) + "\n"
    )
    versions = _h_json(root / release.VERSIONS)
    previous = json.loads(h_blob(release.VERSIONS))
    live = next(v for v in versions["versions"] if v["id"] == versions["default"])
    rechecked = len(upgrade.revision["excluded_outputs_rechecked"])
    assert live["snapshotLabel"] == "Snapshot 2026-10-27"
    assert live["description"].startswith(
        "Scored reference outputs from policyengine-us 2.60.0 ("
    )
    assert (
        f"the {rechecked} that move on 2.60.0 were re-reviewed" in (live["description"])
    )
    assert live["description"].endswith(" - 51 models")
    assert [v for v in versions["versions"] if v is not live] == [
        v for v in previous["versions"] if v["id"] != previous["default"]
    ]
    frozen = root / FROZEN
    pins = driver.upgraded_reference_pins(upgrade)
    for name, pin in pins.items():
        assert sha(frozen / name) == pin, name
    assert (frozen / driver.EXCLUSIONS_NAME).read_text() == upgrade.exclusions_text
    assert (
        sha(root / release.SNAPSHOT / "us_reference_outputs.csv")
        == (upgrade.sha256[driver.CSV_NAME])
    )
    annotations = root / release.ANNOTATIONS
    assert sorted(p.name for p in annotations.iterdir()) == sorted(
        (driver.ADJUDICATIONS, H_ROWS, H_NOTES, EXPLANATIONS, H_AMENDMENTS)
    )
    staged = stage / BUNDLE / "annotations"
    for name in (driver.ADJUDICATIONS, H_ROWS, H_NOTES, EXPLANATIONS):
        assert (annotations / name).read_bytes() == (staged / name).read_bytes()
    assert (annotations / driver.ADJUDICATIONS).read_bytes() == h_blob(
        release.ANNOTATIONS / driver.ADJUDICATIONS
    )
    assert sha(annotations / EXPLANATIONS) == upgrade.sha256[EXPLANATIONS]
    assert (annotations / H_AMENDMENTS).read_bytes() == h_blob(
        release.ANNOTATIONS / H_AMENDMENTS
    )
    serving = _h_json(root / release.SNAPSHOT / "model_serving_config.json")
    base = release.base_serving_config()
    for model, row in base["models"].items():
        assert serving["models"][model] == row
    assert serving["models"][H_TERRA]["evidence"] == {
        "kind": "run_state",
        "run": H_RUN,
    }
    assert serving["evidence_summary"] == {
        "registry": base["evidence_summary"]["registry"],
        "run_state": base["evidence_summary"]["run_state"] + 1,
    }
    assert serving["registry_commit"] == "f" * 40
    manifest = _h_json(root / release.SNAPSHOT / "manifest.json")
    assert manifest["snapshot_date"] == "2026-10-27"
    assert manifest["scope"]["models"] == 51
    assert manifest["model_response_date"] == H_WINDOW
    assert manifest["reference_exclusions"]["outputs"] == 49
    assert manifest["reference_exclusions"]["scored_outputs_per_model"] == 1935
    refresh = manifest["reference_output_refresh"]
    assert refresh["policyengine_us_version"] == "2.60.0"
    assert refresh["reference_csv_sha256"] == upgrade.sha256[driver.CSV_NAME]
    artifact = {key: pointer[key] for key in ("tag", "asset", "url", "sha256", "bytes")}
    assert manifest["published_dashboard_artifact"] == artifact
    assert (
        release.manifest_problems(
            json.loads(h_blob(release.SNAPSHOT / "manifest.json")), manifest, upgrade
        )
        == []
    )
    [configured] = h_stage.board.calls
    assert configured["SNAPSHOT_DATE"] == "2026-10-27"
    assert configured["SOURCE_RUN"] == stage / BUNDLE
    assert configured["SOURCE_ANNOTATIONS"] == staged
    assert configured["REFERENCE_META_SOURCE"] == (
        stage / BUNDLE / "us" / driver.META_NAME
    )
    assert configured["REFERENCE_PINS"] == pins
    assert configured["PUBLISHED_DASHBOARD_SOURCE"] == payload
    assert configured["PUBLISHED_DASHBOARD_ARTIFACT"] == artifact
    assert configured["RUN_STATE_EVIDENCE"] == {
        H_TERRA: str(stage / "inputs" / H_SLUG / "run_state.json")
    }
    assert configured["AUDIT_CASES_DIR"] == stage / "audit/cases"
    assert (stage / "predictions.csv.gz").read_bytes() == (
        frozen / "predictions.csv.gz"
    ).read_bytes()
    cache = root / "app/.cache" / f"dashboard-data-{sha(payload)[:16]}.json"
    assert cache.read_bytes() == payload.read_bytes()


def test_freezing_twice_writes_the_same_files(h_stage):
    """A second freeze of the same stage finds the build's references and this
    release's record where release 20261014's were, and writes the same
    bytes."""
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
        ("base_tag", "does not name release 20261014 as its base"),
        ("base_sha256", "does not name release 20261014 as its base"),
    ],
)
def test_the_freeze_refuses_a_receipt_that_does_not_identify_this_stage(
    h_stage, defect, message
):
    stage = h_stage.stage
    receipt = _h_json(stage / "release-ready.json")
    if defect == "changed":
        case = stage / "audit/cases" / h_stage.board.undecided
        (case / "verdict.json").write_text("{}\n")
    elif defect == "outside_stage":
        pointer = h_stage.workspace / release.POINTER
        receipt["files"][f"../../../{release.POINTER}"] = sha(pointer)
    elif defect == "missing_hashes":
        receipt["files"] = {}
    elif defect == "models":
        receipt["models"] = 50
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
        receipt["base_tag"] = "dashboard-data-20261013b"
    else:
        receipt["base_sha256"] = "0" * 64
    driver.write_json(stage / "release-ready.json", receipt)
    _h_refused(h_stage, message)


def _h_required_evidence(h_stage) -> list[str]:
    case = Path("audit/cases") / h_stage.board.undecided
    names = [Path(driver.BUILD_COPY) / name for name in driver.BUILD_COPY_FILES]
    names += [BUNDLE / "us" / n for n in (*driver.REFERENCE_FILES, "predictions.csv")]
    names += [
        BUNDLE / "annotations" / n
        for n in (driver.ADJUDICATIONS, H_ROWS, H_NOTES, EXPLANATIONS)
    ]
    names += [Path("inputs") / H_SLUG / n for n in driver.PINNED_INPUTS]
    names += [Path(n) for n in ("model-provenance.json", driver.PROMPT_CHANGES)]
    names += [Path("stage.json"), Path("audit/cases.jsonl"), Path("audit/schema.json")]
    names += [case / n for n in ("prompt.md", "verdict.json", "verdict.meta.json")]
    return [str(name) for name in names]


def test_the_receipt_binds_every_file_a_release_gate_reads(h_stage):
    """Without its receipt entry, a staged file could be edited after export
    and its other hashes made to follow; the freeze refuses the missing
    entry, for every file a later gate relies on."""
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
        name = Path("audit/cases") / h_stage.board.undecided / "claude.transcript.jsonl"
        (stage / name).write_text("{}\n")
    else:
        name = Path(driver.AMENDMENTS)
        (stage / name).write_text(json.dumps({"amendments": []}))
    _h_refused(h_stage, f"does not bind.*{re.escape(str(name))}")


def test_the_default_tag_is_the_driver_release_tag(h_stage, monkeypatch):
    """The freeze's tag comes from the driver; a receipt for another tag, or
    a spec for another release, stops it before it writes anything."""
    other = "dashboard-data-20261028"
    monkeypatch.setattr(driver, "RELEASE_TAG", other)
    _h_refused(h_stage, f"release tag '{other}'")
    receipt = _h_json(h_stage.stage / "release-ready.json")
    receipt["release_tag"] = other
    driver.write_json(h_stage.stage / "release-ready.json", receipt)
    _h_refused(h_stage, "names another release or base.*release_tag")


@pytest.mark.parametrize(
    "options",
    [
        ["--tag", "latest"],
        ["--tag", "dashboard-data-2026-10-27"],
        ["--tag", "dashboard-data-20261027bb"],
    ],
    ids=repr,
)
def test_a_tag_that_is_not_a_dated_release_is_refused(h_stage, options):
    before = h_stage.files()
    with pytest.raises(SystemExit):
        h_stage.run(*options)
    assert h_stage.files() == before


def test_a_stage_outside_the_checkout_is_refused(h_stage, tmp_path):
    outside = tmp_path / "elsewhere"
    shutil.copytree(h_stage.stage, outside)
    before = h_stage.files()
    with pytest.raises(SystemExit):
        release.main(["--stage-dir", str(outside), "--dry-run"])
    assert h_stage.files() == before


@pytest.mark.parametrize(
    "field, value, message",
    [
        ("release_tag", "dashboard-data-20261014", "names another release or base"),
        ("base_tag", "dashboard-data-20261013b", "names another release or base"),
        ("base_sha256", "0" * 64, "names another release or base"),
        ("snapshot_date", None, "names no snapshot_date"),
        ("snapshot_date", "2026-10-32", "names no snapshot_date"),
        ("snapshot_date", 20261027, "names no snapshot_date"),
    ],
)
def test_a_spec_for_another_release_or_without_its_date_stops_the_freeze(
    h_stage, monkeypatch, field, value, message
):
    spec = driver.load_spec()
    if value is None:
        del spec[field]
    else:
        spec[field] = value
    monkeypatch.setattr(driver, "load_spec", lambda: copy.deepcopy(spec))
    _h_refused(h_stage, message)


@pytest.mark.parametrize("field", ["early", "partial"])
@pytest.mark.parametrize("value", [True, "missing", None, "false"], ids=repr)
def test_a_rehearsal_stage_rebound_after_export_is_refused_by_main(
    h_stage, field, value
):
    """Review r1, finding 3, through main: an otherwise releasable stage whose
    stage.json marks it early or partial (or leaves the flag unset or not a
    boolean), with its receipt hash refreshed, is refused by the freeze and by
    its dry run before either writes anything."""
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


def _h_edit_terra_score(country: dict) -> list[str]:
    row = country["modelStats"][-1]
    assert row["model"] == H_TERRA
    row.update(exact=100.0, score=100.0)
    at = f"payload.countries.us.modelStats[50 {H_TERRA}]"
    return [f"{at}.score", f"{at}.exact"]


def _h_edit_incumbent_cost(country: dict) -> list[str]:
    row = country["modelStats"][0]
    row["costUsd"] *= 2
    return [f"payload.countries.us.modelStats[0 {row['model']}].costUsd"]


def _h_edit_case_class(country: dict) -> list[str]:
    case = country["scenarioPredictions"]["scenario_000"]["snap"][H_INCUMBENT]
    case["failureSource"] = "prompt_ambiguity"
    return [
        f"payload.countries.us.scenarioPredictions.scenario_000.snap.{H_INCUMBENT}"
        ".failureSource"
    ]


def _h_edit_exclusion_note(country: dict) -> list[str]:
    country["referenceExclusions"][-2]["note"] = "A note no record carries."
    return ["payload.countries.us.referenceExclusions[47].note (only staged)"]


H_PAYLOAD_EDITS = {
    "terra_score": _h_edit_terra_score,
    "incumbent_cost": _h_edit_incumbent_cost,
    "case_class": _h_edit_case_class,
    "exclusion_note": _h_edit_exclusion_note,
}


@pytest.mark.parametrize("edit", H_PAYLOAD_EDITS)
def test_the_freeze_refuses_a_payload_edited_after_export(h_stage, edit):
    """The receipt binds the payload by a hash beside it. Terra's score, an
    incumbent's cost, a case's class or an exclusion's text edited, with that
    hash refreshed, passes the schema, roster and count gates; export's own
    build from the bound bundle does not give it."""
    payload = _h_payload(h_stage)
    paths = H_PAYLOAD_EDITS[edit](payload["countries"]["us"])
    _h_write_payload(h_stage, payload)
    h_stage.rebind(restamp=False)
    refused = _h_refused(h_stage, "is not what export builds")
    for path in paths:
        assert repr(path) in str(refused.value)


@pytest.mark.parametrize(
    "targets, message",
    [
        (
            ("release", "scope", "allowed"),
            "with release 20261014's references and exclusion record, incumbent "
            "modelStats drift",
        ),
        (("release",), "incumbent drift beyond the four approved reference moves"),
    ],
)
def test_the_scope_check_refuses_an_incumbent_the_build_does_not_explain(
    h_stage, targets, message
):
    """An incumbent's cost changed in the bundle itself, so that export's
    build gives the staged payload: with release 20261014's references and
    record put back it is not that release's, and on the build alone the
    change is not the build's."""
    payload = _h_payload(h_stage)
    model = payload["countries"]["us"]["modelStats"][0]["model"]
    for board in (payload, *(h_stage.board.exports[name] for name in targets)):
        row = board["countries"]["us"]["modelStats"][0]
        assert row["model"] == model
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
    "fifty_rows": (
        lambda country: country["modelStats"].pop(),
        "exactly 51 no-tools model rows",
    ),
    "tools_condition": (
        lambda country: country["modelStats"][3].update(condition="tools"),
        "exactly 51 no-tools model rows",
    ),
    "renamed_incumbent": (
        lambda country: country["modelStats"][0].update(model="claude-impostor-1"),
        "roster disagree",
    ),
    "scored_1934": (
        lambda country: country["modelStats"][-1].update(n=1934),
        "scored on 1935 outputs",
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


def _h_case(h_stage, case=None) -> Path:
    return h_stage.stage / "audit/cases" / (case or h_stage.board.undecided)


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
        ("other_seed", "audit seed is not release 20261014's"),
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
    case = _h_case(h_stage)
    if defect == "edited_kept":
        verdict = _h_json(case / "verdict.json")
        verdict["rationale"] = "A rationale the judge never wrote."
        write_json(case / "verdict.json", verdict)
        _h_rebind_verdict(case)
    elif defect == "other_models":
        verdict = _h_json(case / "verdict.json")
        verdict["models"][0]["failure_source"] = "prompt_ambiguity"
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


def test_a_manifest_claiming_terra_on_a_kept_case_is_refused(h_stage):
    """cases.jsonl is editable: a kept case recorded as one Terra got wrong
    (its verdict naming Terra too, every hash following) is refused, since
    Terra's staged prediction is right on it."""
    stage = h_stage.stage
    case = _h_case(h_stage)
    manifest = [
        json.loads(line)
        for line in (stage / "audit/cases.jsonl").read_text().splitlines()
    ]
    for item in manifest:
        if item["case_id"] == case.name:
            item["wrong_models"].append(H_TERRA)
    (stage / "audit/cases.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in manifest)
    )
    changes = _h_json(stage / driver.PROMPT_CHANGES)
    changes["kept"].remove(case.name)
    changes["changed"].append(case.name)
    driver.write_json(stage / driver.PROMPT_CHANGES, changes)
    prompt = case / "prompt.md"
    prompt.write_text(prompt.read_text() + "GPT-6.1 Terra answered too.\n")
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, "wrong models disagree with the staged predictions")


def _h_edit_rows(path: Path, model: str, column: str, value: str) -> None:
    import pandas as pd

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    frame.loc[frame["model"] == model, column] = value
    path.write_text(frame.to_csv(index=False))


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
            record[H_TERRA]["predictions_sha256"] = "0" * 64
        else:
            record[H_TERRA]["treatment_fingerprint"]["request_timeout_seconds"] += 1
        driver.write_json(stage / "model-provenance.json", record)
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, message)


@pytest.mark.parametrize(
    "column, value",
    [("estimated_cost_usd", "0.0002"), ("elapsed_seconds", "9.5"), ("prediction", "1")],
)
def test_terra_rows_edited_in_the_bundle_are_refused(h_stage, column, value):
    """Terra's cost, latency or answers changed in the bundle's predictions,
    with stage.json and model-provenance.json following, are not its pinned
    run's rows, column by column."""
    _h_edit_rows(h_stage.stage / BUNDLE / "us/predictions.csv", H_TERRA, column, value)
    h_stage.rebind()
    refused = _h_refused(h_stage, "rows in the bundle's predictions are not the pinned")
    assert column in str(refused.value)


def test_a_terra_run_file_edited_with_the_bundle_is_refused(h_stage):
    """The run file and the bundle edited together, every stage hash
    following, are not the run file the committed pins name."""
    for path in (
        h_stage.stage / "inputs" / H_SLUG / "predictions.csv",
        h_stage.stage / BUNDLE / "us/predictions.csv",
    ):
        _h_edit_rows(path, H_TERRA, "estimated_cost_usd", "0.0002")
    h_stage.rebind()
    _h_refused(h_stage, f"staged inputs/{H_SLUG}/predictions.csv is not the run file")


def test_input_pins_that_differ_from_their_commit_are_refused(h_stage):
    """The pins file edited in the working tree, not committed, is refused."""
    path = h_stage.workspace / driver.INPUT_PINS_PATH
    path.write_text(path.read_text().replace(H_RUN, "terra-runs/other"))
    _h_refused(h_stage, "differs from its HEAD commit")


def test_input_pins_must_name_the_supervised_run(h_stage):
    """The frozen serving evidence names Terra's supervised run from the
    committed pins, which must give it as <runs root>/terra/run."""
    path = h_stage.workspace / driver.INPUT_PINS_PATH
    path.write_text(path.read_text().replace(f"{H_RUN}/run", "terra-runs/run"))
    h_stage.board.committed[driver.INPUT_PINS_PATH] = path.read_bytes()
    _h_refused(h_stage, "does not name the supervised run of terra")


def _h_annotations(h_stage) -> Path:
    return h_stage.stage / BUNDLE / "annotations"


def _h_edit_annotation(path: Path, case: str, column: str, value: str) -> str:
    import pandas as pd

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    _, scenario, variable = case.split("__")
    mask = (frame.scenario_id == scenario) & (frame.variable == variable)
    assert mask.sum() == 1
    old = frame.loc[mask, column].item()
    frame.loc[mask, column] = value
    path.write_text(frame.to_csv(index=False))
    return old


def test_the_staged_annotations_are_triages_rebuilt_frames(h_stage):
    """The freeze's rebuild of the row annotations and case notes from the
    verdicts and the staged record (verify_annotation_amendments) gives the
    bytes the real triage wrote, every decided case's class applied."""
    import pandas as pd

    annotations = _h_annotations(h_stage)
    release.verify_annotation_amendments(annotations, [], h_stage.stage / "audit")
    notes = pd.read_csv(annotations / H_NOTES, dtype=str, keep_default_na=False)
    decided = _h_decided_cases()
    assert len(notes) == len(decided) + 1
    for row in notes.itertuples():
        case = f"us__{row.scenario_id}__{row.variable}"
        expected = (
            decided[case]["adjudicated_failure_source"]
            if case in decided
            else "llm_error"
        )
        assert row.case_failure_sources == expected, case


@pytest.mark.parametrize(
    "name, column, value, at",
    [
        (H_NOTES, "case_failure_sources", "prompt_ambiguity", "case_failure_sources"),
        (H_ROWS, "failure_source", "prompt_ambiguity", "failure_source"),
        (H_NOTES, "reference_suspect", "True", "reference_suspect"),
        (H_ROWS, "annotation", "A diagnosis no judge wrote.", "annotation"),
    ],
)
def test_the_freeze_refuses_an_annotation_no_judge_or_decision_gave(
    h_stage, name, column, value, at
):
    """On the case no adjudication decides, a failure class, a flag or a
    diagnosis edited in the published annotations, with the receipt's hash
    following, is not what triage builds from the verdicts and the record."""
    case = h_stage.board.undecided
    _h_edit_annotation(_h_annotations(h_stage) / name, case, column, value)
    h_stage.rebind(restamp=False)
    refused = _h_refused(
        h_stage, rf"Staged {re.escape(name)} is not what triage builds"
    )
    assert f"us__{case.split('__', 1)[1]}" in str(refused.value)
    assert at in str(refused.value)


def test_the_freeze_refuses_a_case_note_without_its_adjudication_sentence(h_stage):
    """A decided case's note must carry its decision's exact sentence."""
    decided = sorted(_h_decided_cases())[0]
    path = _h_annotations(h_stage) / H_NOTES
    old = _h_edit_annotation(path, decided, "case_annotation", "A shorter note.")
    assert old != "A shorter note."
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, f"Staged {H_NOTES} is not what triage builds")


def _h_record(h_stage) -> dict:
    return _h_json(_h_annotations(h_stage) / driver.ADJUDICATIONS)


def _h_write_record(h_stage, record: dict) -> None:
    (_h_annotations(h_stage) / driver.ADJUDICATIONS).write_text(
        driver.record_text(record)
    )


def _h_scored_entry(record: dict) -> dict:
    return next(
        e for e in record["adjudications"] if not e.get("excluded_from_scoring")
    )


def _h_excluded_entry(record: dict) -> dict:
    return next(e for e in record["adjudications"] if e.get("excluded_from_scoring"))


H_CHANGED_DECISION = (
    "change recorded decisions beyond the re-judged cases' judge fields"
)
H_RECORD_EDITS = {
    "dropped_decision": (
        lambda r: r["adjudications"].remove(_h_scored_entry(r)),
        "drop recorded decisions",
    ),
    "adjudicated_class": (
        lambda r: _h_scored_entry(r).update(adjudicated_failure_subtype="other"),
        H_CHANGED_DECISION,
    ),
    "judge_class": (
        lambda r: _h_excluded_entry(r).update(judge_failure_subtype="other"),
        H_CHANGED_DECISION,
    ),
    "reasoning": (
        lambda r: _h_scored_entry(r).update(reasoning="Reasoning nobody gave."),
        H_CHANGED_DECISION,
    ),
    "note": (
        lambda r: r.update(note="Another note."),
        "changes its note, schema or date conventions",
    ),
    # The record's own parser refuses an ambiguous output left scored.
    "unexcluded": (
        lambda r: _h_excluded_entry(r).update(excluded_from_scoring=False),
        "requires excluded_from_scoring",
    ),
}


@pytest.mark.parametrize("edit", H_RECORD_EDITS)
def test_the_freeze_refuses_an_adjudication_record_the_release_does_not_give(
    h_stage, edit
):
    """The staged record is release 20261014's: no decision dropped, and no
    adjudicated or judge class, reasoning, note or exclusion changed (no case
    here was re-opened, and the build adds and regenerates none), each with
    the receipt's hash following."""
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


@pytest.mark.parametrize(
    "target, message",
    [
        ("narratives", "is not the installed build's"),
        ("retained", "installed build's .* changed"),
        ("record", "references_installed is not the installed build's record"),
        ("drops", "dropped adjudications are not the regenerated records'"),
        ("no_drops", "stage.json records no dropped adjudications"),
        ("exclusions", "stage.json does not record the release's 49 exclusions"),
        ("scoring", "is not the installed build's"),
    ],
)
def test_the_freeze_regates_the_installed_build_on_the_stage(h_stage, target, message):
    """The installed build is gated again from the stage: its narratives in
    the bundle, its retained files, stage.json's record of it, the drops it
    records and the exclusions it installed, and the scoring source, each
    with the receipt's hash following."""
    stage = h_stage.stage
    prepared = _h_json(stage / "stage.json")
    if target == "narratives":
        path = _h_annotations(h_stage) / EXPLANATIONS
        path.write_bytes(path.read_bytes().replace(b"the ", b"thee ", 1))
    elif target == "retained":
        path = stage / driver.BUILD_COPY / driver.ACTIONS_NAME
        path.write_bytes(path.read_bytes() + b"\n")
    elif target == "record":
        prepared["references_installed"]["scored_outputs"] = 1934
    elif target == "drops":
        entry = _h_excluded_entry(driver.base_adjudication_record())
        prepared["adjudications_dropped"] = [
            {"case_id": driver.case_id(entry), "reason": "Regenerated.", "entry": entry}
        ]
    elif target == "no_drops":
        del prepared["adjudications_dropped"]
    elif target == "exclusions":
        prepared["exclusions_installed"]["records"] = 48
    else:
        path = stage / "scoring" / driver.CSV_NAME
        path.write_bytes(h_blob(FROZEN / driver.CSV_NAME))
    if target in ("record", "drops", "no_drops", "exclusions"):
        driver.write_json(stage / "stage.json", prepared)
    h_stage.rebind(restamp=False)
    _h_refused(h_stage, message)


def test_a_changed_held_reference_record_is_refused(h_stage):
    path = h_stage.workspace / "reference_audit/held_references.json"
    path.write_bytes(path.read_bytes() + b" ")
    _h_refused(h_stage, "held_references.json changed from the base release")


@pytest.mark.parametrize("where", ["base", "stage"])
def test_an_incumbent_prediction_change_is_refused_before_mutation(h_stage, where):
    """The incumbent's rows are release 20261014's (MOCK baseline here),
    whether the change is in the baseline's rows or in the bundle's, every
    stage hash following."""
    if where == "base":
        board = h_stage.board
        lines = board.baseline.splitlines(keepends=True)
        row = lines[1].split(",")
        row[3] = str(float(row[3]) + 1)
        board.baseline = "".join([lines[0], ",".join(row), *lines[2:]])
    else:
        path = h_stage.stage / BUNDLE / "us/predictions.csv"
        lines = path.read_text().splitlines(keepends=True)
        row = lines[1].split(",")
        assert row[0] == H_INCUMBENT
        row[3] = str(float(row[3]) + 1)
        path.write_text("".join([lines[0], ",".join(row), *lines[2:]]))
        h_stage.rebind()
    _h_refused(h_stage, f"Incumbent prediction evidence changed: {H_INCUMBENT}")


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
    """Terra's pinned run itself incomplete, stopped, another model's or
    without its treatment, every pin and hash following it."""
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


def test_a_terra_answer_timed_before_the_response_window_is_refused(h_stage):
    """A request the run records before the configured response start, every
    pin and hash following, stops the freeze before it writes the pointer."""
    for path in (
        h_stage.stage / "inputs" / H_SLUG / "predictions.csv",
        h_stage.stage / BUNDLE / "us/predictions.csv",
    ):
        _h_edit_rows(path, H_TERRA, "request_started_at", "1780000000.0")
    h_stage.rebind(repin=True)
    _h_refused(h_stage, "before the configured model response start")


@pytest.mark.parametrize(
    "defect, message",
    [
        ("other_exclusions", "Frozen reference_exclusions.json is not the installed"),
        ("base_reference", "Frozen reference_outputs.csv is not the installed"),
        ("base_csv_copy", "Frozen us_reference_outputs.csv is not the installed"),
        ("other_record", f"frozen {driver.ADJUDICATIONS} is not the staged one"),
        ("extra_annotation", "Frozen annotation files are not the release's"),
        ("serving_row", f"Frozen serving configuration.*{H_INCUMBENT} is not"),
        ("terra_registry", f"Missing frozen run-state evidence for {H_TERRA}"),
        ("outside", r"changes outside the release: \['population_weight_artifact"),
        ("pinned_reference", r"outside the release: \['source_run_artifacts\..*sce"),
        ("explanations_pin", f"does not state the release.*files.{EXPLANATIONS}"),
        ("models_50", "does not state the release.*'scope.models': 50"),
        ("window", "does not state the release.*model_response_date"),
        ("refresh", "does not state the release.*policyengine_us_version"),
        ("other_predictions", "The predictions asset is not the frozen predictions"),
    ],
)
def test_the_freeze_refuses_what_the_freezer_wrote_outside_the_release(
    h_stage, defect, message
):
    h_stage.board.defects.add(defect)
    with pytest.raises(SystemExit, match=message):
        h_stage.run()


def _h_frozen_arguments(h_stage) -> dict:
    root = h_stage.workspace
    serving = release.base_serving_config()
    return dict(
        stage=h_stage.stage,
        snapshot=root / release.SNAPSHOT,
        annotations=root / release.ANNOTATIONS,
        exclusions_sha256=h_stage.upgrade.sha256[driver.EXCLUSIONS_NAME],
        pointer=_h_json(root / release.POINTER),
        window=H_WINDOW,
        snapshot_date="2026-10-27",
        previous_serving=serving,
        incumbents=set(serving["models"]),
        runs={H_SLUG: H_RUN},
        upgrade=h_stage.upgrade,
    )


@pytest.mark.parametrize(
    "change, message",
    [
        ({"window": "2026-06-12 to 2026-10-23"}, "model_response_date"),
        ({"snapshot_date": "2026-10-28"}, "snapshot_date"),
        ({"runs": {H_SLUG: "terra-runs/elsewhere"}}, "evidence names run"),
        (
            {
                "pointer": {
                    "tag": "x",
                    "asset": "x",
                    "url": "x",
                    "sha256": "x",
                    "bytes": 1,
                }
            },
            "published_dashboard_artifact",
        ),
    ],
    ids=["window", "date", "run", "pointer"],
)
def test_verify_frozen_checks_the_release_the_freeze_derived(h_stage, change, message):
    """After a freeze, verify_frozen passes on what it wrote and refuses
    another window, snapshot date, supervised run, exclusion pin or
    artifact than the freeze derived."""
    h_stage.run()
    arguments = _h_frozen_arguments(h_stage)
    release.verify_frozen(**arguments)
    with pytest.raises(SystemExit, match=message):
        release.verify_frozen(**{**arguments, **change})


@pytest.mark.parametrize("bound", [False, True])
def test_freeze_refuses_a_rebound_shadow_without_touching_stage(h_stage, bound):
    import pandas as pd

    shadow = h_stage.stage / BUNDLE / "us/by_model/shadow.csv"
    shadow.parent.mkdir()
    frame = pd.read_csv(h_stage.stage / BUNDLE / "us/predictions.csv")
    frame.loc[frame.model == H_TERRA, "total_cost_usd"] = 0
    frame.to_csv(shadow, index=False)
    payload = _h_payload(h_stage)
    terra = next(
        r for r in payload["countries"]["us"]["modelStats"] if r["model"] == H_TERRA
    )
    terra.update(costUsd=0.0, costPerHousehold=0.0)
    _h_write_payload(h_stage, payload)
    h_stage.rebind()
    if bound:
        receipt_path = h_stage.stage / "release-ready.json"
        receipt = _h_json(receipt_path)
        receipt["files"][str(shadow.relative_to(h_stage.stage))] = sha(shadow)
        write_json(receipt_path, receipt)
    _h_refused(h_stage, "by_model would shadow")


@pytest.mark.parametrize("numeric", [True, False])
def test_rebound_parse_flag_is_refused_at_export_and_freeze(
    h_stage, monkeypatch, numeric
):
    from policybench.adjudications import apply_adjudications
    from policybench.audit import collect_audit

    case_id = _h_rejudge(h_stage, monkeypatch, new_case=True, adjudicated=False)
    stage = h_stage.stage
    audit = stage / "audit"
    items = [
        json.loads(line) for line in (audit / "cases.jsonl").read_text().splitlines()
    ]
    item = next(row for row in items if row["case_id"] == case_id)
    item["parse_failure_only"] = numeric
    if numeric:
        changes = _h_json(stage / driver.PROMPT_CHANGES)
        changes["added"].remove(case_id)
        write_json(stage / driver.PROMPT_CHANGES, changes)
        record = driver.judge_provenance_record(audit / "cases", frozenset())
        driver.write_json(driver.JUDGE_PROVENANCE, record)
        for name in ("verdict.json", "verdict.meta.json", "claude.transcript.jsonl"):
            (audit / "cases" / case_id / name).unlink()
    else:
        _, scenario, variable = case_id.split("__")
        for path in (
            stage / "inputs" / H_SLUG / "predictions.csv",
            stage / BUNDLE / "us/predictions.csv",
        ):
            with path.open(newline="") as stream:
                rows = list(csv.DictReader(stream))
            for row in rows:
                if row["scenario_id"] == scenario and row["variable"] == variable:
                    row["prediction"] = ""
            path.write_text(_h_csv([H_COLUMNS, *[list(row.values()) for row in rows]]))
    (audit / "cases.jsonl").write_text("".join(json.dumps(row) + "\n" for row in items))
    out = collect_audit(stage / BUNDLE / "us", audit)
    annotations = stage / BUNDLE / "annotations"
    adjudications = freezer.load_adjudications(annotations / driver.ADJUDICATIONS)
    cases = out["case"].rename(
        columns={
            "case_failure_source": "case_failure_sources",
            "case_failure_subtype": "case_failure_subtypes",
        }
    )
    rows, cases, _ = apply_adjudications(out["row"], cases, adjudications)
    driver.amend_annotations(rows, cases, [])
    (annotations / H_ROWS).write_text(driver.annotation_csv_text(rows))
    (annotations / H_NOTES).write_text(driver.annotation_csv_text(cases))
    h_stage.rebind(repin=True)
    # Regenerate the synthetic exporter's payload and bind the current annotations.
    payload = driver.build_payload(
        stage / BUNDLE, copy.deepcopy(h_stage.board.live), upgrade=h_stage.upgrade
    )
    _h_write_payload(h_stage, payload)
    h_stage.rebind()
    before = h_stage.files()
    args = SimpleNamespace(stage_dir=stage, partial=False, early=False)
    with pytest.raises(SystemExit, match="parse_failure_only disagrees"):
        driver.export(args, stage / BUNDLE, copy.deepcopy(h_stage.board.live))
    assert h_stage.files() == before
    _h_refused(h_stage, "parse_failure_only disagrees")


def test_cli_export_refuses_a_shadow_without_invalidating_its_receipt(
    h_stage, monkeypatch
):
    stage = h_stage.stage
    shadow = stage / BUNDLE / "us/by_model"
    shadow.mkdir()
    shutil.copyfile(stage / BUNDLE / "us/predictions.csv", shadow / "shadow.csv")
    monkeypatch.setattr(driver, "ROOT", h_stage.workspace)
    before = h_stage.files()
    with pytest.raises(SystemExit, match="by_model would shadow"):
        driver.main(["--stage-dir", str(stage), "--step", "export"])
    assert h_stage.files() == before
