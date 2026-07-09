"""Tests for CLI argument-parsing helpers."""

import pytest

from policybench.cli import _parse_models, _parse_programs, _slice_scenarios
from policybench.config import MODELS, PROGRAMS


def test_parse_models_defaults_to_full_set():
    assert _parse_models(None) == MODELS
    assert _parse_models([]) == MODELS


def test_parse_models_selects_subset():
    name = next(iter(MODELS))
    assert _parse_models([name]) == {name: MODELS[name]}


def test_parse_models_selects_gpt_56_model():
    name = "gpt-5.6-sol"
    assert _parse_models([name]) == {name: MODELS[name]}


def test_parse_models_unknown_raises():
    with pytest.raises(SystemExit, match="Unknown model"):
        _parse_models(["not-a-real-model"])


def test_parse_programs_defaults_and_validates():
    assert _parse_programs(None) == PROGRAMS
    valid = PROGRAMS[0]
    assert _parse_programs([valid]) == [valid]


def test_parse_programs_unknown_raises():
    with pytest.raises(SystemExit, match="Unknown program"):
        _parse_programs(["not_a_program"])


def test_parse_programs_respects_allowed_set():
    allowed = ["alpha", "beta"]
    assert _parse_programs(["alpha"], allowed=allowed) == ["alpha"]
    with pytest.raises(SystemExit, match="Unknown program"):
        _parse_programs(["gamma"], allowed=allowed)


def test_slice_scenarios_bounds():
    items = [0, 1, 2, 3, 4]
    assert _slice_scenarios(items, 1, 3) == [1, 2]
    assert _slice_scenarios(items, 2, None) == [2, 3, 4]


def test_slice_scenarios_rejects_negative_start():
    with pytest.raises(SystemExit, match="--scenario-start"):
        _slice_scenarios([1, 2, 3], -1, None)


def test_slice_scenarios_rejects_end_before_start():
    with pytest.raises(SystemExit, match="--scenario-end"):
        _slice_scenarios([1, 2, 3], 3, 2)
