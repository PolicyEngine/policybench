"""Render the consensus-flag reports as the Markdown table the README quotes.

Reads consensus_flags.json (default parameters) and consensus_flags_prototype.json
(the 2026-10-05 prototype), marks which cells the prototype flags, which another
audit covers (covered_elsewhere.json), and writes verification/flags_table.md.

  .venv/bin/python reference_audit/2026-10-05-reference-adversary/scripts/flags_table.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


def _fmt(value: float) -> str:
    return f"{value:,.2f}" if value != int(value) else f"{int(value):,}"


def main() -> None:
    default = json.loads((HERE / "consensus_flags.json").read_text())
    prototype = json.loads((HERE / "consensus_flags_prototype.json").read_text())
    covered = {
        (cell["scenario_id"], cell["variable"]): cell["label"]
        for cell in json.loads((HERE / "covered_elsewhere.json").read_text())
    }
    in_prototype = {(f["scenario_id"], f["variable"]) for f in prototype["flags"]}
    lines = [
        f"Default parameters: {json.dumps(default['params'])}",
        "",
        f"Prototype parameters: {json.dumps(prototype['params'])}",
        "",
        f"Payload: `{default['source']}` (sha256 `{default['source_sha256']}`); "
        f"{default['models']} models; top {len(default['top_models'])}: "
        f"{', '.join(default['top_models'])}.",
        "",
        f"Default flags {default['flagged_cells']} of {default['scored_cells']} "
        f"scored cells; the prototype flags {prototype['flagged_cells']}.",
        "",
        "| # | Cell | State | Reference | Cluster answer (models, of top 5) | "
        "Exact | Prototype | Covered by |",
        "|---:|---|---|---:|---|---:|:---:|---|",
    ]
    for index, flag in enumerate(default["flags"], start=1):
        key = (flag["scenario_id"], flag["variable"])
        clusters = "; ".join(
            f"{_fmt(c['answer'])} ({c['n_models']}, {c['n_top']})"
            for c in flag["clusters"]
        )
        lines.append(
            f"| {index} | {flag['scenario_id']} {flag['variable']} | {flag['state']} "
            f"| {_fmt(flag['reference'])} | {clusters} | {flag['models_exact']} "
            f"| {'yes' if key in in_prototype else ''} "
            f"| {covered.get(key, '')} |"
        )
    missing = in_prototype - {(f["scenario_id"], f["variable"]) for f in default["flags"]}
    if missing:
        raise SystemExit(f"prototype flags absent from the default report: {missing}")
    out = HERE / "verification" / "flags_table.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
