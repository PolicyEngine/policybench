"""Rewrite the reference explanations of the outputs the second engine upgrade
changed; every other row of the explanations CSV keeps its bytes.

Adapted from reference_audit/2026-09-28/scripts/narratives_latest.py. The writer
is every reference narrative's (policybench.case_reference_explanations:
REFERENCE_MODEL claude-haiku-4-5, TEMPERATURE, MAX_TOKENS, _prompt), given the
build's engine trace (reference_traces.json from build_references_upgrade.py) and
the change's recorded basis as grounding. A new exclusion is grounded on its
record's alternative reading, as in 2026-09-28. The narrative must state the new
reference value (an amount; a flag states none); a draft that omits it is retried
twice, then refused. --hand-corrected takes a JSON object
{"scenario_id|variable": text} that replaces the writer for a listed output; its
text must also state the value.

--reuse-from <earlier build dir> --reuse-explanations <its narratives CSV> keeps
an earlier build's narrative for an output whose writer inputs are the same in
both builds: the value, the change's cause and grounding, the PolicyEngine
variable and the trace, byte for byte. On another engine the narrative must
also not name the earlier engine's version. Judges' prompts render the narrative, so a reused one
keeps a case's verdict through a rebuild on a newer engine. The reused rows are
listed beside --out (<out>.reused.json) with both builds' sidecar sha256.

The rows rewritten are exactly the sidecar's last revision's changed list (a
reference that changed by more than EPS); each gets the new reference_value,
trace_lines and explanation, and an empty error. Judge prompts render a case's
reference value and explanation, so these are the cases whose verdicts
prepare_audit drops and the judge re-runs.

The writer is Anthropic's, through litellm: the run needs ANTHROPIC_API_KEY and
never an OpenAI key (the script removes OPENAI_API_KEY from its environment):

  ANTHROPIC_API_KEY=$(agent-secret get ANTHROPIC_API_KEY maxghenis) \\
    PYTHONPATH=<checkout> <venv>/bin/python narratives_upgrade.py \\
      --references <build out-dir> \\
      --explanations annotations/<run>/us_case_reference_explanations.csv \\
      --out <csv>
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from build_references_upgrade import (  # noqa: E402
    BASE_COMMIT,
    BASE_SHA256,
    RUN,
    YEAR,
    Refusal,
    format_row,
    git_blob,
    physical_lines,
    sha256_bytes,
)

FIELDS = [
    "country",
    "scenario_id",
    "variable",
    "reference_value",
    "trace_lines",
    "explanation",
    "error",
]
RETRIES = 2


def money(value: float) -> str:
    return f"{value:,.2f}".removesuffix(".00")


# A dollar amount as a narrative writes it: "$1,916.61", "$0", "-$12.50".
DOLLARS = re.compile(r"(-)?\$\s?(\d[\d,]*(?:\.\d+)?)")


def required(item: dict) -> list[float]:
    """What the narrative must state: the new amount; nothing for a flag."""
    if item["variable"].endswith("_eligible"):
        return []
    return [float(item["regenerated"])]


def states_amount(text: str, value: float) -> bool:
    """Whether ``text`` states ``value`` as a dollar amount, to the cent. A
    bare number does not count: for a $0 reference, "2026" states nothing."""
    for sign, number in DOLLARS.findall(text):
        amount = float(number.replace(",", "")) * (-1 if sign else 1)
        if abs(amount - value) <= 0.005 + 1e-9:
            return True
    return False


def missing_amounts(item: dict, text: str) -> list[str]:
    return [money(v) for v in required(item) if not states_amount(text, v)]


def engine_note(engine: str) -> str:
    return (
        f" PolicyEngine here is {engine} with the benchmark's conventions for law "
        "published before July 3, 2026."
    )


def grounding_for(item: dict, records: dict) -> str:
    """The change's recorded basis; a new exclusion's record reading instead."""
    record = records.get((item["scenario_id"], item["variable"]))
    if record is not None and item["cause"] == f"excluded_{record['reason_code']}":
        if record["reason_code"] == "reference_depends_on_unlisted_input":
            return (
                "PolicyBench does not score this output, because the reference "
                "depends on an input the prompt does not state. "
                + record["alternative_reading"]
            )
        return (
            "PolicyBench does not score this output. " + record["alternative_reading"]
        )
    return item["basis"]


def parse_rows(text: str) -> tuple[str, list[tuple[list[str], str]]]:
    """The header line and each record with its raw text."""
    lines = physical_lines(text)
    reader = csv.reader(iter(lines))
    records, used = [], 0
    for fields in reader:
        records.append((fields, "".join(lines[used : reader.line_num])))
        used = reader.line_num
    (header, header_raw), body = records[0], records[1:]
    if header != FIELDS:
        raise Refusal(f"unexpected explanations header {header}")
    return header_raw, body


def rewrite_explanations(text: str, rewrites: dict) -> str:
    """``text`` with each listed (scenario_id, variable) row replaced by
    (reference_value, trace_lines, explanation); every other row byte for byte."""
    header_raw, body = parse_rows(text)
    keys = [(fields[1], fields[2]) for fields, _ in body]
    for key in rewrites:
        if keys.count(key) != 1:
            raise Refusal(f"{key} is in the explanations {keys.count(key)} times")
    parts = [header_raw]
    for fields, raw in body:
        key = (fields[1], fields[2])
        if key not in rewrites:
            parts.append(raw)
            continue
        value, n_lines, explanation = rewrites[key]
        row = format_row(
            [
                fields[0],
                key[0],
                key[1],
                repr(float(value)),
                str(n_lines),
                explanation,
                "",
            ]
        )
        parts.append(row if raw.endswith("\n") else row.removesuffix("\n"))
    out = "".join(parts)
    # Every row the rewrite does not name keeps its bytes.
    _, written = parse_rows(out)
    for (old, old_raw), (new, new_raw) in zip(body, written, strict=True):
        if (old[1], old[2]) not in rewrites and old_raw != new_raw:
            raise Refusal(f"row {(old[1], old[2])} changed")
    return out


def strip_heading(text: str) -> str:
    text = text.strip()
    lines = text.split("\n")
    if lines and lines[0].lstrip().startswith("#"):
        text = "\n".join(lines[1:]).strip()
    return text


def write_narratives(
    references: Path,
    explanations_text: str,
    scenarios,
    *,
    completion,
    hand_corrected: dict | None = None,
    reuse: dict | None = None,
) -> tuple[str, list[tuple]]:
    """The explanations CSV with every changed output's narrative rewritten,
    and the rewritten rows. ``completion`` is litellm.completion (mocked in
    tests). ``reuse`` maps an output to the earlier narrative reusable_narratives
    found for it; the writer is not called for those."""
    from policybench.case_reference_explanations import (
        MAX_TOKENS,
        REFERENCE_MODEL,
        TEMPERATURE,
        _prompt,
        _scenario_summary,
    )

    if not REFERENCE_MODEL.startswith("claude-"):
        raise Refusal(
            f"the narrative writer must be Anthropic's, not {REFERENCE_MODEL}"
        )
    meta = json.loads((references / "reference_outputs.csv.meta.json").read_text())
    upgrade = meta["revisions"][-1]
    if (
        upgrade["kind"] != "engine_upgrade"
        or len([r for r in meta["revisions"] if r["kind"] == "engine_upgrade"]) < 2
    ):
        raise Refusal("the sidecar's last revision is not the second engine upgrade")
    traces = json.loads((references / "reference_traces.json").read_text())
    exclusions = json.loads((references / "reference_exclusions.json").read_text())
    records = {(e["scenario_id"], e["variable"]): e for e in exclusions["exclusions"]}
    note = engine_note(upgrade["engine_version"])
    hand_corrected = hand_corrected or {}
    reuse = reuse or {}
    by_id = scenarios.set_index("scenario_id", drop=False)

    def write(item: dict, extra: str = "") -> str:
        key = (item["scenario_id"], item["variable"])
        traced = traces[f"{key[0]}|{key[1]}"]
        prompt = _prompt(
            "us",
            _scenario_summary(by_id.loc[key[0]]),
            key[1],
            traced["pe_variable"],
            item["regenerated"],
            YEAR,
            traced["trace"],
            grounding=grounding_for(item, records) + note + extra,
        )
        response = completion(
            model=REFERENCE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        return strip_heading(response.choices[0].message.content)

    rewrites, results = {}, []
    for item in upgrade["changed"]:
        key = (item["scenario_id"], item["variable"])
        n_lines = len(traces[f"{key[0]}|{key[1]}"]["trace"].splitlines())
        listed = f"{key[0]}|{key[1]}"
        if listed in hand_corrected:
            text = hand_corrected[listed]
        elif key in reuse:
            text = reuse[key]
        else:
            text = write(item)
            for _ in range(RETRIES):
                missing = missing_amounts(item, text)
                if not missing:
                    break
                text = write(
                    item,
                    " The narrative must state the value "
                    + ", ".join(f"${m}" for m in missing)
                    + ".",
                )
        missing = missing_amounts(item, text)
        if missing:
            raise Refusal(f"{key[0]} {key[1]}: the narrative omits {missing}")
        rewrites[key] = (item["regenerated"], n_lines, text)
        results.append((key[0], key[1], item["regenerated"], n_lines, text))
    unused = set(hand_corrected) - {f"{k[0]}|{k[1]}" for k in rewrites}
    if unused:
        raise Refusal(f"hand-corrected outputs the upgrade did not change: {unused}")
    return rewrite_explanations(explanations_text, rewrites), results


def writer_inputs(references: Path) -> dict:
    """Each changed output's narrative-writer inputs in a build, by output:
    value, cause, grounding, PolicyEngine variable and trace."""
    meta = json.loads((references / "reference_outputs.csv.meta.json").read_text())
    traces = json.loads((references / "reference_traces.json").read_text())
    exclusions = json.loads((references / "reference_exclusions.json").read_text())
    records = {(e["scenario_id"], e["variable"]): e for e in exclusions["exclusions"]}
    inputs = {}
    for item in meta["revisions"][-1]["changed"]:
        key = (item["scenario_id"], item["variable"])
        traced = traces[f"{key[0]}|{key[1]}"]
        inputs[key] = (
            repr(float(item["regenerated"])),
            item["cause"],
            grounding_for(item, records),
            traced["pe_variable"],
            traced["trace"],
        )
    return inputs


def reusable_narratives(
    references: Path, earlier: Path, earlier_explanations_text: str
) -> dict:
    """The earlier build's narratives for outputs whose writer inputs both
    builds share and whose narrative does not name the earlier engine."""
    def engine(path: Path) -> str:
        meta = json.loads((path / "reference_outputs.csv.meta.json").read_text())
        return meta["revisions"][-1]["engine_version"]

    now, then = engine(references), engine(earlier)
    number = then.removeprefix("policyengine-us ")
    current = writer_inputs(references)
    # The groundings name their build's engine; that name may differ, nothing else.
    before = {
        key: (*inputs[:2], inputs[2].replace(then, now), *inputs[3:])
        for key, inputs in writer_inputs(earlier).items()
    }
    _, body = parse_rows(earlier_explanations_text)
    rows: dict = {}
    for fields, _ in body:
        rows.setdefault((fields[1], fields[2]), []).append(fields)
    # The CSV must be the earlier build's narratives: each output that build
    # changed appears once, for the US, with no error, at that build's value.
    # Each value must parse to a finite number: abs(nan - x) > 1e-6 is false,
    # so a "nan" would pass a bare comparison.
    wrong = sorted(
        key
        for key, inputs in writer_inputs(earlier).items()
        if len(rows.get(key, [])) != 1
        or rows[key][0][0] != "us"
        or rows[key][0][6] != ""
        or (stated := finite(rows[key][0][3])) is None
        or (value := finite(inputs[0])) is None
        or abs(stated - value) > 1e-6
    )
    if wrong:
        raise Refusal(
            "--reuse-explanations is not --reuse-from's narratives: "
            f"{[f'{k[0]}|{k[1]}' for k in wrong[:5]]}"
        )
    narratives = {key: found[0][5] for key, found in rows.items()}
    # A narrative naming the earlier engine is stale on another engine, and
    # still true on the same one.
    return {
        key: narratives[key]
        for key, inputs in current.items()
        if before.get(key) == inputs and (then == now or number not in narratives[key])
    }


def finite(text) -> float | None:
    """A value's text as a finite float, or None (unparsable, nan or inf)."""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def main(argv: list[str] | None = None) -> None:
    import pandas as pd

    parser = argparse.ArgumentParser()
    parser.add_argument("--references", required=True)
    parser.add_argument("--explanations", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--hand-corrected")
    parser.add_argument("--reuse-from")
    parser.add_argument("--reuse-explanations")
    args = parser.parse_args(argv)
    if bool(args.reuse_from) != bool(args.reuse_explanations):
        parser.error("--reuse-from and --reuse-explanations go together")
    os.environ.pop("OPENAI_API_KEY", None)
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise Refusal(
            "set ANTHROPIC_API_KEY (agent-secret get ANTHROPIC_API_KEY maxghenis)"
        )
    import litellm

    raw = git_blob(BASE_COMMIT, f"{RUN}/scenarios.csv")
    if sha256_bytes(raw) != BASE_SHA256["scenarios.csv"]:
        raise Refusal("scenarios.csv at the base commit does not match its pin")
    scenarios = pd.read_csv(io.StringIO(raw.decode()))
    hand = (
        json.loads(Path(args.hand_corrected).read_text()) if args.hand_corrected else {}
    )
    reuse = {}
    if args.reuse_from:
        reuse = reusable_narratives(
            Path(args.references),
            Path(args.reuse_from),
            Path(args.reuse_explanations).read_text(),
        )
        reuse = {k: v for k, v in reuse.items() if f"{k[0]}|{k[1]}" not in hand}
    text, results = write_narratives(
        Path(args.references),
        Path(args.explanations).read_text(),
        scenarios,
        completion=litellm.completion,
        hand_corrected=hand,
        reuse=reuse,
    )
    Path(args.out).write_text(text)
    if args.reuse_from:
        sidecar = "reference_outputs.csv.meta.json"
        Path(args.out + ".reused.json").write_text(
            json.dumps(
                {
                    "reused": [f"{k[0]}|{k[1]}" for k in sorted(reuse)],
                    "from_sidecar_sha256": sha256_bytes(
                        (Path(args.reuse_from) / sidecar).read_bytes()
                    ),
                    "into_sidecar_sha256": sha256_bytes(
                        (Path(args.references) / sidecar).read_bytes()
                    ),
                },
                indent=2,
            )
            + "\n"
        )
        print(f"reused {len(reuse)} narratives from {args.reuse_from}")
    for scenario_id, variable, value, _, narrative in results:
        print(f"--- {scenario_id} {variable} ({value:,.2f})\n{narrative}\n")
    print(f"rewrote {len(results)} narratives -> {args.out}")


if __name__ == "__main__":
    main()
