"""Draft unlisted-input exclusions for outputs that rest on the engine's assumed Medicare Part B premium.

Reads the sweep (sweep_part_b.py) and the frozen run's predictions and writes
``proposed_exclusions.json``: one ``reference_depends_on_unlisted_input`` record, in the
format of the frozen run's ``reference_exclusions.json``, for every scored output that
the ``no_part_b`` reading moves by more than the $1 exact-match tolerance (a binary
output, if it flips).

An output that PolicyEngine/policybench#191 (the state income tax in SALT audit,
reference_audit/2026-10-05 on its branch) already proposes to exclude cannot take a
second record: the loader refuses duplicate keys. For such an output the file gives a
standalone Part B record to install only if #191's record is not adopted.

The records are a proposal. They change published scores, so they wait for Max's
ruling; ``decided_on`` is the date the proposal was drafted and a release sets it to
the ruling's date.

  PYTHONPATH=<checkout> <triage>/.venv-pe21517/bin/python \\
    reference_audit/2026-10-05-medicare-part-b/scripts/propose_exclusions.py
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
SUMMARY = HERE / "verification/sweep_part_b_summary.json"
HOUSEHOLDS = HERE / "verification/sweep_part_b_households.json"
OUT = HERE / "proposed_exclusions.json"
ANSWERS = HERE / "verification/model_answers.csv"
MODEL_META = ROOT / "app/src/modelMeta.ts"
# PolicyEngine/policybench#191 at the head this audit read.
SALT_PR = "PolicyEngine/policybench#191"
SALT_HEAD = "8af912a062dd7ae1373de4c043ae2727d3406930"
# reference_audit/2026-10-05/proposed_exclusions.json at SALT_HEAD, kept here so the
# script does not depend on #191's branch.
SALT_COPY = HERE / "verification/inputs/pr191_proposed_exclusions.json"
SALT_SHA256 = "3c330177762c46fa5c52b02f9f943e9d5a65e15855280b64e9b462ab27413272"
SALT_DECISION = "d963"
DRAFTED_ON = "2026-10-05"
ENGINE = "policyengine-us 2.15.17"
FEDERAL = "federal_income_tax_before_refundable_credits"
STATE = "state_income_tax_before_refundable_credits"
TOLERANCE = 1.0
UNLISTED_INPUT = (
    "Medicare enrollment and a Medicare Part B premium paid during 2026, which the "
    "medical expense deductions count; policyengine-us treats every Medicare-eligible "
    "person as enrolled (takes_up_medicare_if_eligible defaults to true, so "
    "medicare_enrolled follows is_medicare_eligible) and adds the modeled premium "
    "(medicare_part_b_premium) to medical expenses, and the household data never set "
    "either"
)
SALT_READINGS = {
    "estimate": "the withholding estimate the reference uses",
    "liability": "the household's state liability",
    "zero": "no state income tax paid",
    "zero_no_local_sales": "no state income tax paid and no local sales tax estimate",
}


def money(value: float) -> str:
    return f"${value:,.2f}"


def listed(value: float) -> str:
    """A listed input, as the prompt prints it (whole dollars)."""
    return f"${value:,.0f}"


def model_labels() -> dict[str, str]:
    """The dashboard's display names (app/src/modelMeta.ts MODEL_LABELS)."""
    text = MODEL_META.read_text()
    block = text.split("export const MODEL_LABELS", 1)[1].split("};", 1)[0]
    return dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', block))


def salt_proposal() -> dict:
    if hashlib.sha256(SALT_COPY.read_bytes()).hexdigest() != SALT_SHA256:
        raise SystemExit(f"{SALT_COPY} does not match #191's file at {SALT_HEAD}")
    return json.loads(SALT_COPY.read_text())


def model_answers(rows: list[dict], household: dict) -> pd.DataFrame:
    """Every model's answer on each moved output, tagged with the readings it matches."""
    predictions = pd.read_csv(RUN / "predictions.csv.gz", low_memory=False)
    out = []
    for row in rows:
        sid, variable = row["scenario_id"], row["variable"]
        values = {"frozen": row["reference"]}
        for key, cell in household[sid]["grid"].items():
            values[key] = cell["outputs"][variable]
        sub = predictions[
            (predictions["scenario_id"] == sid) & (predictions["variable"] == variable)
        ]
        for answer in sub.itertuples():
            matches = (
                []
                if pd.isna(answer.prediction)
                else [
                    key
                    for key, value in values.items()
                    if abs(float(answer.prediction) - value) <= TOLERANCE
                ]
            )
            out.append(
                {
                    "scenario_id": sid,
                    "variable": variable,
                    "model": answer.model,
                    "prediction": answer.prediction,
                    "within_1_of": ";".join(matches),
                }
            )
    return pd.DataFrame(out).sort_values(["scenario_id", "variable", "prediction"])


def within(answers: pd.DataFrame, sid: str, variable: str, reading: str) -> list[dict]:
    sub = answers[
        (answers["scenario_id"] == sid)
        & (answers["variable"] == variable)
        & answers["within_1_of"].str.split(";").apply(lambda keys: reading in keys)
    ]
    return [
        {"model": r.model, "prediction": float(r.prediction)} for r in sub.itertuples()
    ]


def answer_text(models: list[dict]) -> str:
    if not models:
        return "no model"
    labels = model_labels()
    return " and ".join(
        f"{labels[m['model']]} ({money(m['prediction'])})" for m in models
    )


def record(row: dict, household: dict, summary: dict, answers: pd.DataFrame) -> dict:
    sid, variable = row["scenario_id"], row["variable"]
    base = household["baseline_units"]
    person = household["baseline_person"]
    no_b = household["readings"]["no_part_b"]["units"]
    grid = household["grid"]
    head_age = int(person["age"]["head"])
    premium = sum(person["medicare_part_b_premium"].values())
    other = sum(person["other_medical_expenses"].values())
    agi = base["adjusted_gross_income"]
    is_state = variable == STATE
    alternative = grid["no_part_b|estimate"]["outputs"][variable]
    not_enrolled = household["readings"]["not_enrolled"]["outputs"][variable]
    assert abs(alternative - row["value"]) < 1e-6
    assert abs(not_enrolled - alternative) < 1e-6
    # The note says no income-related amount would apply at 2026 MAGI.
    irmaa = household["readings"]["irmaa_from_2026_income"]["person"]
    assert (
        irmaa["gross_medicare_part_b_premium"]
        == person["gross_medicare_part_b_premium"]
    )
    assert person["gross_medicare_part_b_premium"] == person["base_part_b_premium"]
    salt_values = {
        part_b: {
            salt: grid[f"{part_b}|{salt}"]["outputs"][variable]
            for salt in SALT_READINGS
        }
        for part_b in ("modeled", "no_part_b")
    }
    itemizes = {key: bool(cell["itemizes"]) for key, cell in grid.items()}
    where = (
        ", and Virginia's itemized deductions, which start from the federal itemized "
        "deductions (va_itemized_deductions), carry it too"
        if is_state
        else ""
    )
    alternative_reading = (
        "The prompt lists no Medicare enrollment and no Medicare Part B premium, and its "
        "rules say to treat any unlisted numeric input as 0 and not to infer unlisted "
        "expenses or health coverage. The reference counts a modeled Part B premium as a "
        "medical expense: policyengine-us treats the head (age "
        f"{head_age}, so Medicare-eligible) as enrolled because "
        "takes_up_medicare_if_eligible defaults to true, and "
        "medical_expense_health_insurance_premiums adds medicare_part_b_premium, the "
        f"2026 standard premium of $202.90 a month, {money(premium)}, to the listed "
        f"{listed(other)} of other medical expenses. The household itemizes, so the "
        "federal medical expense deduction (26 U.S.C. 213(a): expenses above 7.5% of "
        f"AGI) counts it{where}. The prompt also says to assume program take-up when "
        "required, and a reader who takes a 69-year-old with Social Security "
        "retirement income to be enrolled in Part B and paying the standard premium "
        "gets the frozen value. But the benchmark sets take-up only for the programs "
        "its household data list (Medicaid, SSI, the ACA credit, the DC property tax "
        "credit, the EITC, SNAP and tax filing; policybench.scenarios."
        "DEFAULT_TAKEUP_INPUTS), and Medicare is not among them; the Medicare request "
        "asks only whether the head is eligible; and the more specific rules against "
        "inferring unlisted expenses or health coverage point the other way. Read with "
        f"no Part B premium paid, the deduction falls by {money(premium)} and the "
        "output is the alternative value."
    )
    msp_households = sorted(
        set(summary["medicare_households"]) - set(summary["part_b_households"])
    )
    assert {sid for sid, _ in summary["msp_part_b_coverage_people"]} == set(
        msp_households
    )
    note = (
        "Found 2026-10-05 by sweeping every reference with each person's Medicare Part B "
        "premium at 0, and again with Medicare enrollment off "
        "(reference_audit/2026-10-05-medicare-part-b/scripts/sweep_part_b.py, on "
        "policyengine-us 2.15.17 with latest_final; its baseline reproduces all "
        f"{summary['scored_outputs']:,} scored references). Of "
        f"{summary['medicare_eligible_people']} Medicare-eligible people in "
        f"{len(summary['medicare_households'])} households, the engine charges the "
        f"premium in {len(summary['part_b_households'])} (Medicare Savings Program "
        f"coverage pays it for the {len(summary['msp_part_b_coverage_people'])} eligible "
        f"people in the other {len(msp_households)}); only this household's two tax "
        "outputs move, under either reading. The "
        f"federal medical expense deduction is {money(base['medical_expense_deduction'])} "
        f"in the reference ({money(base['itemized_medical_expenses'])} of expenses less "
        f"7.5% of {money(agi)} AGI) and {money(no_b['medical_expense_deduction'])} "
        "without the premium; the household itemizes under both. "
    )
    no_b = salt_values["no_part_b"]
    if is_state:
        assert abs(no_b["estimate"] - no_b["liability"]) < 1e-6
        assert abs(no_b["zero"] - no_b["zero_no_local_sales"]) < 1e-6
        assert len({round(v, 6) for v in salt_values["modeled"].values()}) == 1
        note += (
            "The output also depends on the state income tax in the federal SALT "
            f"deduction, which {SALT_PR} proposes to treat as an unlisted input "
            f"(decision {SALT_DECISION}), through the federal itemization election, which "
            "Virginia follows (va_deductions reads tax_unit_itemizes). Without the "
            f"premium the output is {money(no_b['estimate'])} under both the "
            "withholding estimate and the liability; with no state income tax paid it "
            f"is {money(no_b['zero'])}, with or without the local sales "
            "tax estimate, because the household then takes the federal and Virginia "
            "standard deductions. With the premium it is "
            f"{money(salt_values['modeled']['estimate'])} under all four readings. "
        )
    else:
        note += (
            "Under the readings of the state income tax in SALT that "
            f"{SALT_PR} sets out, without the premium the output is "
            f"{money(salt_values['no_part_b']['liability'])} under the liability and "
            f"{money(salt_values['no_part_b']['zero'])} with no state income tax paid "
            "(the household then takes the standard deduction). "
        )
    note += (
        "The premium is the standard premium: the engine reads the income-related "
        "adjustment from MAGI two years earlier, which no household sets, and at this "
        f"household's 2026 MAGI ({money(agi + base['tax_exempt_interest_income'])}) none "
        "would apply. "
    )
    alt_models = within(answers, sid, variable, "no_part_b|estimate")
    frozen_models = within(answers, sid, variable, "frozen")
    sentence = (
        f"{answer_text(alt_models)} answered within $1 of the alternative value, and "
        f"{answer_text(frozen_models)} within $1 of the frozen value."
    )
    note += sentence[0].upper() + sentence[1:]
    if not is_state:
        liability_models = within(answers, sid, variable, "no_part_b|liability")
        literal_models = within(answers, sid, variable, "no_part_b|zero")
        note += (
            f" {answer_text(liability_models)} answered within $1 of the value with no "
            "premium and the liability, and "
            f"{answer_text(literal_models)} within $1 of the value with no premium and "
            "no state income tax paid."
        )
    return {
        "scenario_id": sid,
        "variable": variable,
        "reason_code": "reference_depends_on_unlisted_input",
        "alternative_reading": alternative_reading,
        "frozen_value": row["reference"],
        "alternative_value": alternative,
        "engine_version": ENGINE,
        "decided_on": DRAFTED_ON,
        "decided_by": "developer",
        "unlisted_input": UNLISTED_INPUT,
        "note": note,
        "_readings": {
            "salt_by_part_b": salt_values,
            "itemizes": itemizes,
            "not_enrolled": not_enrolled,
        },
    }


def main() -> None:
    summary = json.loads(SUMMARY.read_text())
    households = {
        h["scenario_id"]: h for h in json.loads(HOUSEHOLDS.read_text())["households"]
    }
    if summary["scored_reference_mismatches"]:
        raise SystemExit("the sweep's baseline does not reproduce the references")
    frozen = json.loads((RUN / "reference_exclusions.json").read_text())["exclusions"]
    frozen_keys = {(e["scenario_id"], e["variable"]) for e in frozen}
    salt = salt_proposal()
    salt_keys = {(e["scenario_id"], e["variable"]): e for e in salt["exclusions"]}

    moved = summary["moved"]["no_part_b"]
    for reading in ("not_enrolled", "not_enrolled_direct"):
        other = {(m["scenario_id"], m["variable"]) for m in summary["moved"][reading]}
        if other != {(m["scenario_id"], m["variable"]) for m in moved}:
            raise SystemExit(f"{reading} moves a different set of outputs")
    answers = model_answers(moved, households)
    answers.to_csv(ANSWERS, index=False)

    exclusions, conditional, already = [], [], []
    for row in moved:
        key = (row["scenario_id"], row["variable"])
        if key in frozen_keys:
            already.append(key)
            continue
        entry = record(row, households[row["scenario_id"]], summary, answers)
        readings = entry.pop("_readings")
        if key in salt_keys:
            salt_record = salt_keys[key]
            conditional.append(
                {
                    "record": entry,
                    "readings": readings,
                    "install_if": (
                        f"{SALT_PR}'s record for this output (decision {SALT_DECISION}) "
                        "is not adopted. The output then still rests on the Part B "
                        "premium and needs this record."
                    ),
                    "if_salt_record_adopted": (
                        f"{SALT_PR}'s record already excludes the output, and its note "
                        "already gives the values without the premium (it quotes "
                        f"{money(readings['salt_by_part_b']['no_part_b']['estimate'])}, "
                        f"{money(readings['salt_by_part_b']['no_part_b']['liability'])} "
                        f"and {money(readings['salt_by_part_b']['no_part_b']['zero'])}). "
                        "A release adds the unlisted input to that record's "
                        "unlisted_input text: '; also " + UNLISTED_INPUT + "'."
                    ),
                    "salt_record_frozen_value": salt_record["frozen_value"],
                    "salt_record_alternative_value": salt_record["alternative_value"],
                }
            )
        else:
            entry["_readings"] = readings
            exclusions.append(entry)
    if already:
        raise SystemExit(f"already-excluded outputs moved; add note text: {already}")

    readings = {}
    for entry in exclusions:
        readings[f"{entry['scenario_id']}/{entry['variable']}"] = entry.pop("_readings")
    payload = {
        "schema_version": 1,
        "status": (
            f"proposed {DRAFTED_ON}; changes published scores, so it waits for Max's "
            "ruling (cos decision). decided_on is the draft date; a release sets it to "
            "the ruling's date."
        ),
        "basis": (
            "policybench/reference_exclusions.py: an output is excluded for every model "
            "when its reference depends on an engine input the prompt never listed and "
            "a careful reader could take the stated facts the other way."
        ),
        "salt_proposal": {
            "pr": SALT_PR,
            "head": SALT_HEAD,
            "decision": SALT_DECISION,
            "outputs": [f"{s}/{v}" for s, v in salt_keys],
        },
        "exclusions": exclusions,
        "conditional_on_salt_decision": conditional,
        "already_excluded": [],
        "readings": readings,
        "readings_moving_no_further_output": [
            "not_enrolled",
            "not_enrolled_direct",
            "irmaa_from_2026_income",
        ],
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(json.dumps(payload, indent=1))
    print(answers.to_string(index=False))


if __name__ == "__main__":
    main()
