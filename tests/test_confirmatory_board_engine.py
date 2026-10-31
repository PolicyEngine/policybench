"""Engine sidecars must refuse a calculator start before any provider call."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_confirmatory_run import (
    complete_preflight_design,
    cr,
    pilot,
)
from tests.test_confirmatory_run import (
    fast as _fast_fixture,
)
from tests.test_confirmatory_run import (
    world as _world_fixture,
)

world = _world_fixture
fast = _fast_fixture


REAL_BOARD_ENGINE = pilot.board_engine


def engine_fault(world, tmp_path, monkeypatch, fault):
    w = world(models=(cr.CHEAP[0],))
    design = complete_preflight_design(w, tmp_path)
    metadata = Path(design["board"]) / "reference_outputs.csv.meta.json"
    monkeypatch.setattr(pilot, "board_engine", REAL_BOARD_ENGINE)

    def no_run(*args, **kwargs):
        pytest.fail("a refused preflight must not construct or call a provider")

    monkeypatch.setattr(cr, "Run", no_run)
    monkeypatch.setattr(pilot, "run_household", no_run)
    if fault == "malformed":
        metadata.write_text("{")
    else:
        read_text = Path.read_text

        def denied(path, *args, **kwargs):
            if path == metadata:
                raise PermissionError("engine metadata read denied")
            return read_text(path, *args, **kwargs)

        monkeypatch.setattr(Path, "read_text", denied)
    return w, design, metadata


@pytest.mark.parametrize("fault", ["malformed", "unreadable"])
@pytest.mark.parametrize("entrypoint", ["preflight", "main"])
def test_engine_metadata_refuses_full_calculator_start(
    world, tmp_path, monkeypatch, capsys, fault, entrypoint
):
    w, design, metadata = engine_fault(world, tmp_path, monkeypatch, fault)
    if entrypoint == "preflight":
        problems = cr.preflight(design, (cr.CHEAP[0],))
        # The preflight's own guard, beside the saved-treatment lines it keeps.
        guard = f"{metadata}: cannot read the board's engine: "
        assert sum(problem.startswith(guard) for problem in problems) == 1, problems
        for model in cr.CHEAP:
            assert any(
                problem.startswith(f"no-tools {model}: ")
                and "cannot check saved no-tools treatment" in problem
                and str(metadata) in problem
                for problem in problems
            ), problems
    else:
        design_path = tmp_path / "design.json"
        design_path.write_text(json.dumps(design))
        assert cr.main(["run", str(design_path)]) == 1
        output = capsys.readouterr().out
        assert "The run cannot start" in output
        assert str(metadata) in output
    assert not w.provider.count


@pytest.mark.parametrize("fault", ["malformed", "unreadable"])
def test_main_names_engine_reread_failure_and_preserves_all_problems(
    world, tmp_path, monkeypatch, capsys, fault
):
    w, design, metadata = engine_fault(world, tmp_path, monkeypatch, fault)
    # Isolate main's final engine reread, which must retain preflight's problems.
    monkeypatch.setattr(cr, "preflight", lambda *_: ["earlier preflight problem"])
    design_path = tmp_path / "design.json"
    design_path.write_text(json.dumps(design))
    assert cr.main(["run", str(design_path)]) == 1
    output = capsys.readouterr().out
    assert "The run cannot start" in output
    assert "earlier preflight problem" in output
    assert str(metadata) in output
    assert not w.provider.count
