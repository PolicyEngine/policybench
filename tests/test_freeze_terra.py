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
    prepared = {"references_installed": driver.references_record(upgrade, None)}
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
        json.dumps({"references_installed": installed})
    )
    with pytest.raises(SystemExit, match="installed build"):
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
    }
    seed = {case.name: {"prompt_sha256": "0" * 64, "verdict_sha256": "1" * 64}}
    monkeypatch.setattr(driver, "load_seed", lambda stage: seed)
    write_json(case / "verdict.meta.json", meta)
    release.verify_verdicts(tmp_path)
    if value is None:
        del meta[field]
    else:
        meta[field] = value
    write_json(case / "verdict.meta.json", meta)
    with pytest.raises(SystemExit, match="1 staged verdicts fail validation"):
        release.verify_verdicts(tmp_path)
