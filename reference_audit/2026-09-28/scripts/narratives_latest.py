"""Rewrite the derivation narratives of the outputs the 2026-09-28 upgrade changed.

Same writer as every other reference narrative (policybench.case_reference_explanations:
REFERENCE_MODEL, TEMPERATURE, MAX_TOKENS, _prompt), given the policyengine-us 2.15.17
trace from build_references_latest.py and the reviewed basis of each change as
grounding. The narrative must state the new reference value; a draft that omits it is
retried twice, then refused.

HAND_CORRECTED replaces narratives the writer got wrong, each checked against the
2.15.17 trace (reference_traces.json): 013 (the writer called $240 a monthly benefit
over January-October and said the household met the net income and asset tests; the
trace is $0 in January-February and $24 from March, through categorical eligibility),
008 and 082 (the writer misdescribed how the New Jersey EITC and New York CDCC derive
from the federal credits), 028 (the writer dated the child support fix to 2.15.17).
The frozen narrative of scenario_064 dependent2_chip_eligible said the 18-year-old "exceeds CHIP's age
eligibility threshold". CHIP's age limit is under 19 (gov.hhs.chip.child.max_age); on
2.15.17 with the conventions, medicaid_income_level is 3.215 against Wisconsin's 3.06
CHIP limit, and has_chip_disqualifying_health_coverage is true (has_esi). That wrong
narrative is what the 2026-09-28 judge flag on this case repeated.

  ANTHROPIC_API_KEY=... PYTHONPATH=<policybench checkout> python narratives_latest.py \\
    --references ../reference_v13 --actions latest/final_actions.json \\
    --explanations <annotations>/us_case_reference_explanations.csv --out <csv>
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import pandas as pd

BUNDLE = Path(
    "/Users/maxghenis/PolicyEngine/policybench/results/local/newmodels/publish/"
    "us_full_run_20260612_policyengine_4_16_1_populace/us"
)
YEAR = 2026
ENGINE_NOTE = (
    " PolicyEngine here is policyengine-us 2.15.17 with the benchmark's conventions for "
    "law published before July 3, 2026."
)
HAND_CORRECTED = {
    ("scenario_013", "snap"): (
        "PolicyEngine calculated SNAP benefits of $240 for 2026 for this 80-year-old "
        "disabled Arizonan who lives alone: $0 in January and February and the $24 monthly "
        "minimum from March through December. The household's gross income is $2,539.33 a "
        "month. Under SNAP's ordinary rules it fails the net income test, with net income "
        "of $2,138 a month, and the asset test, with $58,700 in the bank. From March 2026 "
        "Arizona extends SNAP through expanded categorical eligibility to households with "
        "gross income up to 200% of the poverty guideline ($2,608.33 a month, $2,660 from "
        "October), which treats the income and asset tests as met. The ordinary benefit "
        "formula, the $298 maximum less 30% of net income, gives less than nothing, so the "
        "household receives the $24 minimum in each of those ten months."
    ),
    ("scenario_008", "state_refundable_credits"): (
        "PolicyEngine calculated New Jersey refundable credits of $5,842.40 for this "
        "married couple filing jointly with six children. The New Jersey earned income "
        "credit is $3,292.40: 40% of the federal earned income credit, which reaches its "
        "$8,231 maximum for a family with three or more children. The New Jersey child tax "
        "credit is $2,500 under the schedule New Jersey enacted on June 30, 2026 for tax "
        "years 2026 to 2028, which pays more per young child at low taxable income. The "
        "New Jersey property tax credit adds $50."
    ),
    ("scenario_082", "state_refundable_credits"): (
        "PolicyEngine calculated New York refundable credits of $667 for this head of "
        "household with one child aged 1. The Empire State child credit is $307: the "
        "$1,000 credit for a child aged three or younger, reduced by $16.50 for each whole "
        "$1,000 of federal adjusted gross income ($117,652.65) above the $75,000 threshold, "
        "42 steps or $693. New York's child and dependent care credit is $360: 60% of the "
        "federal credit, which is 20% of the $3,000 of care expenses the federal credit "
        "counts for one child."
    ),
    ("scenario_028", "reduced_price_school_meals_eligible"): (
        "PolicyEngine determined that this Pennsylvania household of four is not eligible "
        "for reduced-price school meals. School meals count the household's income of "
        "$61,277: $60,000 of wages, $10 of interest and $1,267 of child support received, "
        "which counts as income for school meals (7 CFR 245.6(a)(5)(ii)). That is 1.86 "
        "times the $33,000 poverty guideline for a household of four, above the 185% limit "
        "for reduced-price meals, so the value is 0."
    ),
    ("scenario_064", "dependent2_chip_eligible"): (
        "PolicyEngine determined that Dependent 2 is not eligible for CHIP in Wisconsin "
        "for 2026. At 18, Dependent 2 is within CHIP's age limit, which covers children "
        "under 19. Two other conditions fail. The household's income is 321.5% of the "
        "federal poverty guideline, above Wisconsin's CHIP limit of 306%. And Dependent 2 "
        "has employer-sponsored insurance, which PolicyEngine counts as coverage that "
        "rules a child out of CHIP. PolicyEngine also finds Dependent 2 not eligible for "
        "Medicaid, so the value is False."
    ),
}


def money(value: float) -> str:
    return f"{value:,.2f}".removesuffix(".00")


def main() -> None:
    import litellm

    from policybench.case_reference_explanations import (
        MAX_TOKENS,
        REFERENCE_MODEL,
        TEMPERATURE,
        _prompt,
        _scenario_summary,
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--references", required=True)
    parser.add_argument("--actions", required=True)
    parser.add_argument("--explanations", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    refs = Path(args.references)
    meta = json.loads((refs / "reference_outputs.csv.meta.json").read_text())
    upgrade = meta["revisions"][-1]
    assert upgrade["kind"] == "engine_upgrade"
    traces = json.loads((refs / "reference_traces.json").read_text())
    actions = json.loads(Path(args.actions).read_text())
    basis = {(a["scenario_id"], a["variable"]): a["basis"] for a in actions["approved"]}
    basis |= {
        (e["scenario_id"], e["variable"]): (
            "PolicyBench does not score this output, because the reference depends on "
            "an input the prompt does not state. " + e["alternative_reading"]
        )
        for e in actions["new_exclusions"]
    }
    scenarios = pd.read_csv(BUNDLE / "scenarios.csv").set_index(
        "scenario_id", drop=False
    )
    explanations = pd.read_csv(args.explanations)

    async def one(item, extra=""):
        key = (item["scenario_id"], item["variable"])
        traced = traces[f"{key[0]}|{key[1]}"]
        prompt = _prompt(
            "us",
            _scenario_summary(scenarios.loc[key[0]]),
            key[1],
            traced["pe_variable"],
            item["regenerated"],
            YEAR,
            traced["trace"],
            grounding=basis.get(key, item["basis"]) + ENGINE_NOTE + extra,
        )
        response = await litellm.acompletion(
            model=REFERENCE_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=TEMPERATURE,
            max_tokens=MAX_TOKENS,
        )
        text = response.choices[0].message.content.strip()
        lines = text.split("\n")
        if lines and lines[0].lstrip().startswith("#"):
            text = "\n".join(lines[1:]).strip()
        return text, len(traced["trace"].splitlines())

    def required(item) -> list[str]:
        if item["variable"].endswith("_eligible"):
            return []
        return [money(item["regenerated"])]

    results = []
    for item in upgrade["changed"]:
        key = (item["scenario_id"], item["variable"])
        if key in HAND_CORRECTED:
            text = HAND_CORRECTED[key]
            assert not [f for f in required(item) if f not in text], key
            n_lines = len(traces[f"{key[0]}|{key[1]}"]["trace"].splitlines())
            results.append((key[0], key[1], item["regenerated"], n_lines, text))
            continue
        text, n_lines = asyncio.run(one(item))
        for _ in range(2):
            missing = [f for f in required(item) if f not in text]
            if not missing:
                break
            text, n_lines = asyncio.run(
                one(item, f" The narrative must state the value {', '.join(missing)}.")
            )
        missing = [f for f in required(item) if f not in text]
        if missing:
            raise SystemExit(
                f"{item['scenario_id']} {item['variable']}: omits {missing}"
            )
        results.append(
            (item["scenario_id"], item["variable"], item["regenerated"], n_lines, text)
        )
    for (scenario_id, variable), text in HAND_CORRECTED.items():
        if (scenario_id, variable) in {(r[0], r[1]) for r in results}:
            continue
        mask = (explanations.scenario_id == scenario_id) & (
            explanations.variable == variable
        )
        value = float(explanations.loc[mask, "reference_value"].iloc[0])
        lines = int(explanations.loc[mask, "trace_lines"].iloc[0])
        results.append((scenario_id, variable, value, lines, text))
    for scenario_id, variable, value, n_lines, text in results:
        mask = (explanations.scenario_id == scenario_id) & (
            explanations.variable == variable
        )
        assert mask.sum() == 1, (scenario_id, variable)
        explanations.loc[mask, "reference_value"] = value
        explanations.loc[mask, "trace_lines"] = n_lines
        explanations.loc[mask, "explanation"] = text
        explanations.loc[mask, "error"] = pd.NA
        print(f"--- {scenario_id} {variable} ({value:,.2f})\n{text}\n")
    explanations.to_csv(args.out, index=False)
    print(f"rewrote {len(results)} narratives -> {args.out}")


if __name__ == "__main__":
    main()
