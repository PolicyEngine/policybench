"""How often a random property test notices a wrong top rate, by income generator.

The audit's first mutation run left a 39 percent top rate standing. This
reproduces why. The property is the one tests/test_tax_table_audit.py states (no
dollar of income is taxed above 37 percent), run against a schedule whose top
rate is 39 percent, 40 times with seeds 0 to 39 and 1,000 examples each, under
two ways of drawing an income:

  cents             one integer of cents from $0 to $1,000,000, as the test first
                    drew it. Hypothesis draws a range wider than 24 bits mostly
                    from its small end, so few draws reach the top bracket.
  dollars_and_cents whole dollars to $2,000,000 and cents drawn apart, as the
                    test draws it now.

A run that raises no failure missed the fault. Writes
verification/top_rate_detection.json.

  uv run python reference_audit/2026-10-10-tax-table/scripts/top_rate_detection.py
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import json
import math
from pathlib import Path

from hypothesis import given, seed, settings
from hypothesis import strategies as st

HERE = Path(__file__).resolve().parents[1]
RUNS = 40
EXAMPLES = 1000
WRONG_RATES = (10, 12, 22, 24, 32, 35, 39)
GENERATORS = {
    "cents": st.integers(min_value=0, max_value=1_000_000 * 100),
    "dollars_and_cents": st.builds(
        lambda dollars, cents: 100 * dollars + cents,
        st.integers(min_value=0, max_value=2_000_000),
        st.integers(min_value=0, max_value=99),
    ),
}


def broken_table():
    path = Path(__file__).with_name("tax_table.py")
    spec = importlib.util.spec_from_file_location("top_rate_tax_table", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.RATES = WRONG_RATES
    return module


def missed(table, incomes, number: int) -> bool:
    """Whether one seeded run of the property passes against the wrong rate."""

    @seed(number)
    @settings(max_examples=EXAMPLES, deadline=None, database=None)
    @given(
        incomes, incomes, st.sampled_from(table.STATUSES), st.sampled_from((2025, 2026))
    )
    def no_dollar_is_taxed_above_37_percent(a, b, status, year):
        low, high = sorted((a, b))
        rise = table.schedule_tax_cents(high, status, year) - table.schedule_tax_cents(
            low, status, year
        )
        assert rise <= math.ceil(0.37 * (high - low)) + 1

    try:
        no_dollar_is_taxed_above_37_percent()
    except AssertionError:
        return False
    return True


def main() -> None:
    table = broken_table()
    result = {
        "hypothesis": importlib.metadata.version("hypothesis"),
        "fault": "the top rate is 39 percent",
        "runs_per_generator": RUNS,
        "examples_per_run": EXAMPLES,
        "seeds": [0, RUNS - 1],
        "runs_that_missed_the_fault": {
            name: sum(missed(table, incomes, number) for number in range(RUNS))
            for name, incomes in GENERATORS.items()
        },
    }
    out = HERE / "verification" / "top_rate_detection.json"
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
