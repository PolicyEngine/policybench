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

Reads the pass's inputs from git, never from the working tree: the frozen run's
predictions and exclusions and the dashboard's model labels as PASS_COMMIT (release
dashboard-data-20260930, #187) holds them, and this audit's sweep and copy of #191's
records as AUDIT_COMMIT (#202, which merged this audit) holds them. Each must match
its pinned sha256 in INPUTS, or the script stops before writing anything. Release
dashboard-data-20261006 (#202) excluded both scenario_114 outputs, so on its run the
script stops on already-excluded outputs.

  PYTHONPATH=<checkout> <triage>/.venv-pe21517/bin/python \\
    reference_audit/2026-10-05-medicare-part-b/scripts/propose_exclusions.py

``--out-dir`` writes proposed_exclusions.json and verification/model_answers.csv under
another directory; tests/test_reference_audit_pins.py regenerates them that way and
requires the committed ones byte for byte.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import subprocess
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT_DIR = HERE
OUT = "proposed_exclusions.json"
ANSWERS = "verification/model_answers.csv"
# The pass's inputs, pinned by commit and sha256.
PASS_COMMIT = "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"
AUDIT_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"
RUN_PATH = (
    "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
AUDIT_PATH = "reference_audit/2026-10-05-medicare-part-b"
SUMMARY_PATH = f"{AUDIT_PATH}/verification/sweep_part_b_summary.json"
HOUSEHOLDS_PATH = f"{AUDIT_PATH}/verification/sweep_part_b_households.json"
MODEL_META_PATH = "app/src/modelMeta.ts"
# PolicyEngine/policybench#191 at the head this audit read.
SALT_PR = "PolicyEngine/policybench#191"
SALT_HEAD = "8af912a062dd7ae1373de4c043ae2727d3406930"
# reference_audit/2026-10-05/proposed_exclusions.json at SALT_HEAD, kept here so the
# script does not depend on #191's branch.
SALT_COPY_PATH = f"{AUDIT_PATH}/verification/inputs/pr191_proposed_exclusions.json"
SALT_SHA256 = "3c330177762c46fa5c52b02f9f943e9d5a65e15855280b64e9b462ab27413272"
# Every file the script reads from the repository: path -> (commit, sha256).
INPUTS = {
    f"{RUN_PATH}/predictions.csv.gz": (
        PASS_COMMIT,
        "ca2c4c48c7fd3e680c9c61a7380ecfcb60ce95f913c5c363762e023949d8ad12",
    ),
    f"{RUN_PATH}/reference_exclusions.json": (
        PASS_COMMIT,
        "bf4e6a249aeee01d0b71f5834ef7a35c4bab2266d2c59d0e81b12a0da44281c2",
    ),
    MODEL_META_PATH: (
        PASS_COMMIT,
        "c2f39f6f891ed93f564534283800bd15e51504ea179097c2a77a9278d0157a00",
    ),
    SUMMARY_PATH: (
        AUDIT_COMMIT,
        "f294a7952ee8a3e6b4e570cba403d84df6ddd8f6ae295fb31e976aaa381526a4",
    ),
    HOUSEHOLDS_PATH: (
        AUDIT_COMMIT,
        "c34bee0320747cba71f33e9a8e00f5c28a6b82473542ce966352d9041554e1aa",
    ),
    SALT_COPY_PATH: (AUDIT_COMMIT, SALT_SHA256),
}
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
    text = pass_input(MODEL_META_PATH).decode()
    block = text.split("export const MODEL_LABELS", 1)[1].split("};", 1)[0]
    return dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', block))


def git_bytes(commit: str, path: str, pinned: str) -> bytes:
    """``path`` as ``commit`` holds it, refusing any other bytes."""
    result = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{commit}:{path}"],
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit(
            f"cannot read {path} at {commit[:12]}; fetch full history "
            f"(git fetch --unshallow): {result.stderr.decode().strip()}"
        )
    digest = hashlib.sha256(result.stdout).hexdigest()
    if digest != pinned:
        raise SystemExit(
            f"{commit[:12]}:{path} has sha256 {digest}, not the pinned {pinned}"
        )
    return result.stdout


def pass_input(path: str) -> bytes:
    """The input at ``path``, as INPUTS pins it."""
    commit, pinned = INPUTS[path]
    return git_bytes(commit, path, pinned)


def salt_proposal() -> dict:
    """#191's proposal at SALT_HEAD, from this audit's copy (SALT_SHA256 pins it)."""
    return json.loads(pass_input(SALT_COPY_PATH))


def model_answers(rows: list[dict], household: dict) -> pd.DataFrame:
    """Every model's answer on each moved output, tagged with the readings it matches."""
    predictions = pd.read_csv(
        io.BytesIO(pass_input(f"{RUN_PATH}/predictions.csv.gz")),
        compression="gzip",
        low_memory=False,
    )
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
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        default=str(OUT_DIR),
        help=f"where to write {OUT} and {ANSWERS} (default: %(default)s)",
    )
    out_dir = Path(parser.parse_args().out_dir)
    # Check every pin before reading anything, so a refused input writes nothing.
    for path in INPUTS:
        pass_input(path)
    summary = json.loads(pass_input(SUMMARY_PATH))
    households = {
        h["scenario_id"]: h
        for h in json.loads(pass_input(HOUSEHOLDS_PATH))["households"]
    }
    if summary["scored_reference_mismatches"]:
        raise SystemExit("the sweep's baseline does not reproduce the references")
    frozen = json.loads(pass_input(f"{RUN_PATH}/reference_exclusions.json"))[
        "exclusions"
    ]
    frozen_keys = {(e["scenario_id"], e["variable"]) for e in frozen}
    salt = salt_proposal()
    salt_keys = {(e["scenario_id"], e["variable"]): e for e in salt["exclusions"]}

    moved = summary["moved"]["no_part_b"]
    for reading in ("not_enrolled", "not_enrolled_direct"):
        other = {(m["scenario_id"], m["variable"]) for m in summary["moved"][reading]}
        if other != {(m["scenario_id"], m["variable"]) for m in moved}:
            raise SystemExit(f"{reading} moves a different set of outputs")
    answers = model_answers(moved, households)
    (out_dir / ANSWERS).parent.mkdir(parents=True, exist_ok=True)
    answers.to_csv(out_dir / ANSWERS, index=False)

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
    (out_dir / OUT).write_text(json.dumps(payload, indent=1) + "\n")
    print(json.dumps(payload, indent=1))
    print(answers.to_string(index=False))


if __name__ == "__main__":
    main()
