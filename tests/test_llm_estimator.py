# tests/test_llm_estimator.py
import pytest
from policybench.llm_estimator import parse_llm_answer


def test_parse_llm_answer_ok():
    raw_text = "The total is $3,500 for 2025"
    val = parse_llm_answer(raw_text)
    # Should parse 3500, ignoring 2025
    assert val == 3500.0


def test_parse_llm_answer_none():
    raw_text = "No numeric here"
    val = parse_llm_answer(raw_text)
    assert val is None
