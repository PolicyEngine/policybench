"""Draft unlisted-input exclusions for outputs that rest on the state withholding estimate.

Reads the sweep (sweep_salt_withholding.py) and the side readings (variants.py) and
writes ``proposed_exclusions.json``: one ``reference_depends_on_unlisted_input``
record, in the format of the frozen run's ``reference_exclusions.json``, for every
scored output that the ``liability`` reading moves by more than the $1 exact-match
tolerance (a binary output, if it flips). Outputs already excluded for another reason
cannot take a second record (the loader refuses duplicate keys); they are listed under
``already_excluded`` with the note text a release should add to their record.

The records are a proposal. They change published scores, so they wait for Max's
ruling; ``decided_on`` is the date the proposal was drafted and a release sets it to
the ruling's date.

Reads the pass's inputs from git, never from the working tree: the frozen run's
exclusions and references as PASS_COMMIT (release dashboard-data-20260930, #187)
holds them, and this audit's sweep and side readings as AUDIT_COMMIT (#202, which
merged this audit) holds them. Each must match its pinned sha256 in INPUTS, or the
script stops before writing anything. Release dashboard-data-20261006 (#202)
installed the three records, so on its run every output would land under
``already_excluded`` and the file would lose its proposals.

  python reference_audit/2026-10-05/scripts/propose_exclusions.py

``--out-dir`` writes the file elsewhere; tests/test_reference_audit_pins.py
regenerates it that way and requires the committed one byte for byte.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
OUT_DIR = HERE
# The pass's inputs, pinned by commit and sha256.
PASS_COMMIT = "8b4c0ca146bb6f66deba6ce24009d49d70d92df2"
AUDIT_COMMIT = "9ce4ade8382962a9134860c23f56d92509b5e57f"
RUN_PATH = (
    "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
AUDIT_PATH = "reference_audit/2026-10-05"
SWEEP_PATH = f"{AUDIT_PATH}/verification/sweep_salt_withholding.csv"
HOUSEHOLDS_PATH = f"{AUDIT_PATH}/verification/sweep_salt_withholding_households.json"
VARIANTS_PATH = f"{AUDIT_PATH}/verification/variants.json"
# Every file the script reads from the repository: path -> (commit, sha256).
INPUTS = {
    f"{RUN_PATH}/reference_exclusions.json": (
        PASS_COMMIT,
        "bf4e6a249aeee01d0b71f5834ef7a35c4bab2266d2c59d0e81b12a0da44281c2",
    ),
    f"{RUN_PATH}/reference_outputs.csv": (
        PASS_COMMIT,
        "e8bbba8fd3e90f78e7c0e83df06227bc1c94563e92f7405fe12be853a30b2466",
    ),
    SWEEP_PATH: (
        AUDIT_COMMIT,
        "5918e349699471b8dcf9baa9584afdd583f8054624301839bb228bdc90a52d0c",
    ),
    HOUSEHOLDS_PATH: (
        AUDIT_COMMIT,
        "b36669b4a6b43483fbec5ce18f2d8affbeda98df34d3523ae39ff2deec0e4e40",
    ),
    VARIANTS_PATH: (
        AUDIT_COMMIT,
        "5cf0588e6071d4c35cfe6f8e07a8f3aaf8873dfbc8b7e34d496813d047141764",
    ),
}
DRAFTED_ON = "2026-10-05"
ENGINE = "policyengine-us 2.15.17"
FEDERAL = "federal_income_tax_before_refundable_credits"
STATE = "state_income_tax_before_refundable_credits"
UNLISTED_INPUT = (
    "state income tax withheld or paid during 2026, which the federal state and local "
    "tax deduction takes as its state income tax part; policyengine-us fills it with "
    "state_withheld_income_tax, a formula estimate on federal AGI that the household "
    "data never set"
)
# How policyengine-us 2.15.17 estimates each state's withholding (the per-state
# *_withheld_income_tax formula), read from the installed package.
PROXY = {
    "CA": (
        "California's single rate schedule applied to the person's whole federal AGI{ss} "
        "less California's single standard deduction, at California's 2025 amounts "
        "(ca_withheld_income_tax, under the c_ca_hold_2025 convention)"
    ),
    "CT": (
        "Connecticut's single rate schedule applied to the person's whole federal AGI "
        "less the maximum single personal exemption (ct_withheld_income_tax)"
    ),
    "MA": (
        "5% of the person's whole federal AGI above the $4,400 single personal "
        "exemption (ma_withheld_income_tax)"
    ),
    "MD": (
        "Maryland's single rate schedule plus the default county's rate, applied to "
        "the person's whole federal AGI less the $3,400 single withholding allowance "
        "(md_withheld_income_tax, under the c_md_2026 convention)"
    ),
    "VA": (
        "Virginia's rate schedule applied to the person's whole federal AGI{ss} less "
        "Virginia's single standard deduction (va_withheld_income_tax)"
    ),
}
STATE_NAME = {
    "CA": "California",
    "CT": "Connecticut",
    "MA": "Massachusetts",
    "MD": "Maryland",
    "VA": "Virginia",
}
# States that exempt Social Security the proxy's federal AGI includes.
EXEMPTS_SOCIAL_SECURITY = {"CA", "VA"}
PAYROLL_AUTHORITY = {
    "CA": "Trujillo v. Commissioner, 68 T.C. 670 (1977)",
    "MA": "Rev. Rul. 2025-4",
    "CT": "Rev. Rul. 2025-4",
}
PAYROLL_LABEL = {
    "CA": "California SDI",
    "MA": "Massachusetts paid family and medical leave",
    "CT": "Connecticut paid leave",
}


def money(value: float) -> str:
    return f"${value:,.2f}"


def reading_text(state: str, base: dict, liability: float) -> str:
    name = STATE_NAME[state]
    social_security = ""
    if (
        state in EXEMPTS_SOCIAL_SECURITY
        and base["tax_unit_taxable_social_security"] > 0
    ):
        social_security = (
            f" (including {money(base['tax_unit_taxable_social_security'])} of taxable "
            f"Social Security, which {name} exempts)"
        )
    county = (
        " plus county income tax"
        if base["md_local_income_tax_before_refundable_credits"]
        else ""
    )
    return (
        "The prompt lists no state income tax withheld or paid during 2026. The "
        "reference fills the state income tax part of the federal state and local tax "
        "deduction (26 U.S.C. 164(a)(3), (b)(5)) with policyengine-us's formula "
        f"estimate of {name} income tax withheld: {PROXY[state].format(ss=social_security)}, "
        f"{money(base['state_withheld_income_tax'])}. The same "
        f"engine computes the household's {name} income tax{county} before refundable "
        f"credits as {money(liability)}. Read as the household paying its 2026 {name} "
        "income tax during the year, the deduction takes that liability and the "
        "output is the alternative value. The prompt's rule that unlisted numeric "
        "inputs are 0 gives a third reading, no state income tax paid, under which "
        "SALT takes the general sales tax (the note gives that value)."
    )


def note_text(sid: str, row: pd.Series, household: dict, variant: dict) -> str:
    base = household["baseline"]
    liability = household["liability"]["diagnostics"]
    zero = household["zero"]["diagnostics"]
    itemizes = base["tax_unit_itemizes"] and liability["tax_unit_itemizes"]
    capped = [
        label
        for label, d in (("the reference", base), ("the alternative", liability))
        if d["salt"] > d["salt_cap"]
    ]
    cap = f"${base['salt_cap']:,.0f}"
    local_sales = zero["local_sales_tax"]
    pieces = [
        "Found 2026-10-05 by sweeping every reference with the state income tax in "
        "SALT read three ways (reference_audit/2026-10-05/scripts/"
        "sweep_salt_withholding.py, on policyengine-us 2.15.17 with latest_final; its "
        "baseline reproduces all 1,928 scored references, and an independent "
        "re-implementation agreed on all 1,984 outputs).",
        f"SALT is {money(base['salt_deduction'])} in the reference and "
        f"{money(liability['salt_deduction'])} under the alternative; the household "
        + ("itemizes under both" if itemizes else "itemizes under only one reading")
        + (
            f", and the {cap} cap binds in {' and '.join(capped)}."
            if capped
            else f", and the {cap} cap binds under neither."
        ),
        "Under the zero reading SALT takes the general sales tax, "
        f"{money(zero['state_and_local_sales_or_income_tax'])}, and the output is "
        f"{money(row['zero'])}"
        + (
            f"; that sales tax includes the engine's local component of "
            f"{money(local_sales)} (20% of the state table amount, an estimate for an "
            "unlisted locality), and without it the output is "
            f"{money(variant['no_local_sales']['zero'][FEDERAL])}."
            if local_sales > 0
            else "."
        ),
    ]
    corrected = variant.get("corrected_liability")
    if corrected:
        pieces.append(
            f"The alternative uses the engine's {STATE_NAME[household['state']]} "
            f"liability ({money(variant['liability'])}), which this household's "
            "state output carries as an engine-defect exclusion; with the corrected "
            f"liability ({money(corrected['withheld'])}"
            + (", recorded on policyengine-us 1.755.4" if sid == "scenario_022" else "")
            + f") the output is {money(corrected['outputs'][FEDERAL])}."
        )
    payroll = variant["employee_state_payroll_tax"]
    if payroll > 0:
        pieces.append(
            "The output also moves under an engine defect: policyengine-us 2.15.17 "
            f"leaves the household's {PAYROLL_LABEL.get(household['state'], 'mandatory state payroll')} "
            f"contributions ({money(payroll)}) out of SALT, though they are deductible "
            f"state income taxes ({PAYROLL_AUTHORITY.get(household['state'], 'Rev. Rul. 2025-4')}). "
            "With them the output is "
            f"{money(variant['payroll_in_salt']['estimate'][FEDERAL])} under the "
            "withholding estimate and "
            f"{money(variant['payroll_in_salt']['liability'][FEDERAL])} under the "
            "liability."
        )
    no_b = variant["no_part_b"]
    if abs(no_b["reference"][FEDERAL] - row["baseline"]) > 1.0:
        text = (
            "The reference's medical deduction also includes a modeled Medicare Part B "
            f"premium of {money(variant['medicare_part_b_premium'])}, which the prompt "
            "does not list. Without it the output is "
            f"{money(no_b['reference'][FEDERAL])} under the withholding estimate"
        )
        if "liability" in no_b:
            text += f" and {money(no_b['liability'][FEDERAL])} under the liability"
        if "literal" in no_b:
            text += (
                ", and with no withholding, local sales tax or Part B premium it is "
                f"{money(no_b['literal'][FEDERAL])}"
                + (
                    " (the household then takes the standard deduction)"
                    if not no_b["literal_itemizes"]
                    else ""
                )
            )
        pieces.append(text + ".")
    return " ".join(pieces)


def already_note(row: pd.Series, household: dict, variant: dict) -> str:
    base = household["baseline"]
    liability = household["liability"]["diagnostics"]
    name = STATE_NAME[household["state"]]
    text = (
        "The output also moves under the state income tax withheld reading (unlisted "
        f"input): the reference's SALT uses the {name} withholding estimate "
        f"({money(base['state_withheld_income_tax'])}); with the engine's own "
        f"liability ({money(variant['liability'])}) the 2.15.17 value is "
        f"{money(row['liability'])}, and with no state income tax paid it is "
        f"{money(row['zero'])}"
    )
    if base["salt"] > base["salt_cap"] and liability["salt"] <= base["salt_cap"]:
        text += (
            f". The ${base['salt_cap']:,.0f} cap that binds in the reference does not "
            "bind under the liability"
        )
    counties = variant.get("md_counties")
    if counties:
        feds = [c[FEDERAL] for c in counties.values()]
        text += (
            ", so the liability value depends on the county, which the prompt does not "
            f"state: {money(min(feds))} to {money(max(feds))} across Maryland's 24 "
            "county rates (the engine's default, Allegany, gives "
            f"{money(counties['ALLEGANY_COUNTY_MD'][FEDERAL])})"
        )
    r02 = variant.get("r02_120")
    if r02:
        text += (
            ". With r02's IRA fix on 2.15.17 the value is "
            f"{money(r02['reference'])} under the withholding estimate, "
            f"{money(r02['liability'])} under the liability and {money(r02['zero'])} "
            "with no state income tax paid"
        )
    payroll = variant["employee_state_payroll_tax"]
    if payroll > 0:
        text += (
            ". policyengine-us 2.15.17 also leaves the household's "
            f"{PAYROLL_LABEL.get(household['state'], 'mandatory state payroll')} "
            f"contributions ({money(payroll)}) out of SALT "
            f"({PAYROLL_AUTHORITY.get(household['state'], 'Rev. Rul. 2025-4')}); with them "
            f"the 2.15.17 value is {money(variant['payroll_in_salt']['estimate'][FEDERAL])}"
        )
    return text + "."


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--out-dir",
        default=str(OUT_DIR),
        help="where to write proposed_exclusions.json (default: %(default)s)",
    )
    out = Path(parser.parse_args().out_dir) / "proposed_exclusions.json"
    # Check every pin before reading anything, so a refused input writes nothing.
    for path in INPUTS:
        pass_input(path)
    sweep = pd.read_csv(io.BytesIO(pass_input(SWEEP_PATH)))
    households = {
        h["scenario_id"]: h
        for h in json.loads(pass_input(HOUSEHOLDS_PATH))["households"]
    }
    variants = {
        v["scenario_id"]: v for v in json.loads(pass_input(VARIANTS_PATH))["households"]
    }
    existing = json.loads(pass_input(f"{RUN_PATH}/reference_exclusions.json"))[
        "exclusions"
    ]
    existing_keys = {(e["scenario_id"], e["variable"]): e for e in existing}
    reference = pd.read_csv(
        io.BytesIO(pass_input(f"{RUN_PATH}/reference_outputs.csv"))
    ).set_index(["scenario_id", "variable"])["value"]

    moved = sweep[sweep["liability_moved"]]
    proposals, already = [], []
    for _, row in moved.iterrows():
        sid, variable = row["scenario_id"], row["variable"]
        key = (sid, variable)
        household = households[sid]
        variant = variants[sid]
        assert abs(variant["liability"] - household["liability"]["withheld"]) < 1e-6
        assert abs(variant["liability_outputs"][variable] - row["liability"]) < 1e-6
        if key in existing_keys:
            entry = existing_keys[key]
            already.append(
                {
                    "scenario_id": sid,
                    "variable": variable,
                    "existing_reason_code": entry["reason_code"],
                    "existing_basis": entry.get("root_cause")
                    or entry.get("unlisted_input"),
                    "reference": float(reference[key]),
                    "engine_value_on_2_15_17": float(row["baseline"]),
                    "liability_reading_value": float(row["liability"]),
                    "zero_reading_value": float(row["zero"]),
                    "note_to_append": already_note(row, household, variant),
                }
            )
            continue
        assert abs(float(reference[key]) - float(row["baseline"])) <= 1e-3, key
        assert household["liability"]["converged"] and household["net"]["converged"]
        base = household["baseline"]
        proposals.append(
            {
                "scenario_id": sid,
                "variable": variable,
                "reason_code": "reference_depends_on_unlisted_input",
                "alternative_reading": reading_text(
                    household["state"], base, variant["liability"]
                ),
                "frozen_value": float(reference[key]),
                "alternative_value": float(row["liability"]),
                "engine_version": ENGINE,
                "decided_on": DRAFTED_ON,
                "decided_by": "developer",
                "unlisted_input": UNLISTED_INPUT,
                "note": note_text(sid, row, household, variant),
            }
        )

    payload = {
        "schema_version": 1,
        "status": (
            "proposed 2026-10-05; changes published scores, so it waits for Max's "
            "ruling (cos decision). decided_on is the draft date; a release sets it to "
            "the ruling's date."
        ),
        "basis": (
            "policybench/reference_exclusions.py: an output is excluded for every "
            "model when its reference depends on an engine input the prompt never "
            "listed and a careful reader could take the stated facts the other way."
        ),
        "exclusions": proposals,
        "already_excluded": already,
        "readings_moving_no_further_scored_output": sorted(
            reading
            for reading in ("net", "zero")
            if set(
                map(
                    tuple,
                    sweep[sweep[f"{reading}_moved"] & ~sweep["excluded"]][
                        ["scenario_id", "variable"]
                    ].values,
                )
            )
            <= {(p["scenario_id"], p["variable"]) for p in proposals}
        ),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"{len(proposals)} proposed, {len(already)} already excluded -> {out}")


if __name__ == "__main__":
    main()
