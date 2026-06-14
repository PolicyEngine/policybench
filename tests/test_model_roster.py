"""Regression tests for the benchmark model roster."""

import re
from pathlib import Path

from policybench.config import MODELS

ROOT = Path(__file__).resolve().parents[1]


def _quoted_values(body: str) -> list[str]:
    return re.findall(r'"([^"]+)"', body)


def test_runbook_model_lists_match_default_roster():
    text = (ROOT / "docs" / "runbook.md").read_text()
    expected = set(MODELS)

    claude_loop = re.search(r"for model in ([^;]+); do", text)
    assert claude_loop is not None
    claude_models = set(claude_loop.group(1).split())
    flag_models = set(re.findall(r"--model ([a-z0-9.\-]+)", text))
    assert claude_models | flag_models == expected

    non_claude_block = re.search(
        r"The current default non-Claude model set is:\n\n```bash\n(.*?)\n```",
        text,
        flags=re.DOTALL,
    )
    assert non_claude_block is not None
    listed_non_claude = {
        line.strip() for line in non_claude_block.group(1).splitlines() if line.strip()
    }
    assert listed_non_claude == {
        model for model in expected if not model.startswith("claude-")
    }


def test_frontend_model_metadata_matches_default_roster():
    text = (ROOT / "app" / "src" / "modelMeta.ts").read_text()
    expected = list(MODELS)

    order_match = re.search(
        r"export const MODEL_ORDER = \[(.*?)\] as const;",
        text,
        flags=re.DOTALL,
    )
    assert order_match is not None
    assert _quoted_values(order_match.group(1)) == expected

    labels_match = re.search(
        r"export const MODEL_LABELS: Record<string, string> = \{(.*?)\};",
        text,
        flags=re.DOTALL,
    )
    assert labels_match is not None
    assert set(expected).issubset(set(_quoted_values(labels_match.group(1))[::2]))

    colors_match = re.search(
        r"export const MODEL_COLORS: Record<string, string> = \{(.*?)\};",
        text,
        flags=re.DOTALL,
    )
    assert colors_match is not None
    assert set(expected).issubset(set(_quoted_values(colors_match.group(1))))
