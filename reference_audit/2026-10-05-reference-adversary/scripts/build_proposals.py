"""Write proposed_changes.json: the exclusion and regeneration records this pass proposes.

Verification (verification/independent/*.md) found four engine defects behind four scored
references and one definition-scope ambiguity behind four more. Each root cause gets an
exclusion alternative and, where the law gives one value, a regeneration alternative.
Nothing here changes a score: a release installs one alternative per root cause only after
Max rules (cos decision). He ruled on 2026-10-06 (d1022, and d994 for the two Louisiana cells
this pass skipped); `status` records both rulings.

Values:
- scenario_018: the engine's own counterfactual with the 2026 indexed deduction
  (verification/probes/az_standard_deduction_scenario_018.json).
- scenario_025, scenario_082: hand computations in verification/independent/oh_025.md and
  ny_082.md, from the engine's own intermediate values in the probes.
- scenario_043: $0, the refund the law allows for tax year 2026.
- scenario_093, scenario_123: the household total over every return its members must file,
  from verification/definition_conformance.json (the engine with the dependent as the head of
  their own tax unit).

  python reference_audit/2026-10-05-reference-adversary/scripts/build_proposals.py
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
RUN = (
    ROOT
    / "paper/snapshot/20260501/runs/us_full_run_20260612_policyengine_4_16_1_populace"
)
OUT = HERE / "proposed_changes.json"
DRAFTED = "2026-10-06"
ENGINE = "policyengine-us 2.15.17"
STATE_TAX = "state_income_tax_before_refundable_credits"
FED_TAX = "federal_income_tax_before_refundable_credits"
RULED = "2026-10-06"
AFTER_RELEASE = "dashboard-data-20261006"
CONFIRMED_CAUSES = [
    "az_standard_deduction_indexing",
    "oh_medical_deduction_premiums",
    "co_sales_tax_refund_surplus",
    "ny_cdcc_606_c2",
]

# Max's rulings, quoted from the cos decision log (~/chief-of-staff/state/decisions).
RULINGS = [
    {
        "decision": "d1022",
        "ruled_at": "2026-10-06T13:11",
        "question": (
            "PolicyBench: exclude the reference-adversary's confirmed cells in the next "
            "release after 20261006 (AZ 018, OH 025, CO 043, NY 082 engine defects; PA 123 "
            "dependent-return scope, 4 cells), regenerate the four defect cells once fixed "
            "policyengine-us versions land; NC 026 refuted"
        ),
        "ruling": "Approved by Max 2026-10-06 in chat ('approve')",
        "next_release": (
            f"exclude every exclusion record below, 8 cells (variant exclude_all), in the "
            f"next release after {AFTER_RELEASE}"
        ),
        "later_release": (
            "regenerate the four defect cells once fixed policyengine-us versions land"
        ),
        "root_causes": [*CONFIRMED_CAUSES, "household_scope_dependent_returns"],
        "unchanged": (
            "scenario_026 child1/child2_medicaid_eligible: the adversary's reference_wrong "
            "was refuted (verification/independent/nc_026.md); both references stand"
        ),
    },
    {
        "decision": "d994",
        "ruled_at": "2026-10-06T13:11",
        "question": (
            "PolicyBench: PR #192's Louisiana documentation sentence, applied as written, "
            "changes five scored references held under the 2026-09-22 conventions (Idaho "
            "zero-rate threshold: scenario_076 -$13.46; SNAP FY2027 standard deduction for "
            "4/5/6+ households: 008 +$9, 038 +$3, 109 +$6; Maryland's 2026 return "
            "deduction on the IRS's reading of 10-217(c): 068 -$2.375, the literal reading "
            "keeps $3,350). Adopt the sentence and regenerate those references in a "
            "follow-up release (and pick Maryland's reading), narrow the sentence so no "
            "hold moves, or keep the current convention letter?"
        ),
        "ruling": (
            "Exclude LA scenario_051 and scenario_077 state income tax; keep the "
            "published-amounts convention (no change to Idaho 076, SNAP 008/038/109, "
            "Maryland 068); v2 states indexed amounts in the prompt. Next release after "
            "20261006. (Max 2026-10-06: approve)"
        ),
        "cells": [
            {"scenario_id": "scenario_051", "variable": STATE_TAX},
            {"scenario_id": "scenario_077", "variable": STATE_TAX},
        ],
        "source": (
            "PolicyEngine/policybench#192 (Louisiana 2026 standard deduction audit). Both "
            "cells were flagged here and skipped as covered elsewhere "
            "(covered_elsewhere.json), so this file carries no records for them."
        ),
    },
]

# Upstream PolicyEngine/policyengine-us fix PRs.
UPSTREAM = {
    "az_standard_deduction_indexing": "to be filed",
    "oh_medical_deduction_premiums": "to be filed",
    "co_sales_tax_refund_surplus": "to be filed",
    "ny_cdcc_606_c2": "to be filed",
}

ROOT_CAUSES = {
    "az_standard_deduction_indexing": {
        "verdict": "CONFIRMED",
        "evidence": "verification/independent/az_018.md",
        "law": "A.R.S. 43-1041(A)(1) and (H), as amended by Laws 2026, Ch. 140 (HB 4168, approved 2026-06-13); 26 U.S.C. 63(c)(7)(B); Rev. Proc. 2025-32 s. 4.14",
        "defect": "policyengine-us puts the Arizona standard deduction's uprating on the parent parameter node, which policyengine-core does not propagate to the filing-status children, so the 2025 amount ($15,750 single) carries into 2026 unindexed",
        "basis": "HB 4168 set the single standard deduction at $15,750 'subject to subsection H', and subsection H requires the department to adjust it 'in the same manner in which the federal basic standard deduction is adjusted for inflation pursuant to section 63'. The federal basic standard deduction starts from the same $15,750 and is $16,100 for 2026 (Rev. Proc. 2025-32), so Arizona's 2026 single deduction is $16,100.",
        "cells": [
            {
                "scenario_id": "scenario_018",
                "variable": STATE_TAX,
                "state": "AZ",
                "corrected": 1137.302246,
                "value_source": "engine counterfactual: policyengine-us 2.15.17 with latest_final and az_standard_deduction = 16,100 (verification/probes/az_standard_deduction_scenario_018.json)",
            }
        ],
    },
    "oh_medical_deduction_premiums": {
        "verdict": "CONFIRMED",
        "evidence": "verification/independent/oh_025.md",
        "law": "R.C. 5747.01(A)(10)(b)-(c) (effective 2026-03-05); 26 U.S.C. 213(d)(1)(D); Ohio IT 1040 instructions, unreimbursed medical and health care expense worksheet line 3",
        "defect": "policyengine-us counts health insurance premiums toward Ohio's 7.5%-of-federal-AGI medical deduction only when the person is Medicare-eligible AND has no employer-paid plan, where Ohio's worksheet line 3 reads 'Medicare or an employer-paid health care plan', so a non-Medicare filer with employer coverage gets no premium credit",
        "basis": "R.C. 5747.01(A)(10)(b) deducts unreimbursed medical care above 7.5% of federal AGI, and (A)(10)(c) defines medical care by IRC 213(d), which includes insurance premiums. The head's $6,500 of after-tax non-employer premiums plus $800 of other medical expenses ($7,300) exceed 7.5% of federal AGI ($7,119.40) by $180.60.",
        "cells": [
            {
                "scenario_id": "scenario_025",
                "variable": STATE_TAX,
                "state": "OH",
                "corrected": 1916.604,
                "value_source": "hand computation from the engine's Ohio AGI, exemptions, rate schedule and retirement income credit (verification/independent/oh_025.md section 4)",
            }
        ],
    },
    "co_sales_tax_refund_surplus": {
        "verdict": "CONFIRMED",
        "evidence": "verification/independent/co_043.md",
        "law": "C.R.S. 39-22-2003(2), 39-22-2002(2)(a), 39-3-209; Colorado Legislative Council Staff forecasts of December 2025, March 2026 and June 2026 (tax year 2026 refund table $0 in every tier); OSPB forecast of 2026-06-18",
        "defect": "policyengine-us pays Colorado's six-tier state sales tax refund without the statute's condition that the fiscal year ending in the tax year had excess state revenues, carrying the tax year 2025 table into 2026",
        "basis": "C.R.S. 39-22-2003(2) allows the refund for a tax year only 'if there were excess state revenues for the fiscal year ending in that tax year'. Each Legislative Council Staff forecast before the freeze (December 2025, March and June 2026) published a tax year 2026 refund table of $0 in every tier, OSPB's June 2026 outlook put FY 2025-26 $15.3 million below the cap and anticipated no refunds, and no pre-freeze official source described a tax year 2026 six-tier refund; the State Controller certified a $175.9 million shortfall on 2026-09-08.",
        "cells": [
            {
                "scenario_id": "scenario_043",
                "variable": "state_refundable_credits",
                "state": "CO",
                "corrected": 0.0,
                "value_source": "law: no tax year 2026 sales tax refund; the household has no other Colorado refundable credit (verification/independent/co_043.md section 5)",
            }
        ],
    },
    "ny_cdcc_606_c2": {
        "verdict": "CONFIRMED",
        "evidence": "verification/independent/ny_082.md",
        "law": "N.Y. Tax Law 606(c)(1) and 606(c-2), as amended and added by L.2026, ch. 59, Part A (S.9009-C/A.10009-C, signed 2026-05-28)",
        "defect": "policyengine-us computes New York's 2026 child and dependent care credit with the pre-2026 formula (a percentage of the federal credit), which L.2026 ch. 59 limited to tax years beginning before 2026 and replaced with the refundable 606(c-2) credit on qualifying expenses",
        "basis": "Tax Law 606(c-2) gives, for tax years beginning on or after 2026-01-01, a refundable credit of the applicable percentage (55%, less 0.00025 percentage points per dollar of New York AGI above $15,000, floor 4%) of qualifying expenses up to $3,000 for one child. At New York AGI of $117,585.15 that is 29.3537% of $3,000 = $880.61, plus the $307 Empire State child credit.",
        "cells": [
            {
                "scenario_id": "scenario_082",
                "variable": "state_refundable_credits",
                "state": "NY",
                "corrected": 1187.611,
                "value_source": "hand computation from the engine's New York AGI and Empire State child credit (verification/independent/ny_082.md section 3)",
            }
        ],
    },
    "household_scope_dependent_returns": {
        "verdict": "AMBIGUOUS",
        "evidence": "verification/independent/pa_123.md; verification/definition_conformance.md (household scope)",
        "law": "72 P.S. 7302(a); 2025 PA-40 instructions p. 3 (a minor with PA income over $33 must file); 26 U.S.C. 73(a); RSMo 143.011",
        "unlisted_input": "whether the income tax outputs cover only the head and spouse's return or every return the household's members must file; the definitions name no return, and a dependent here must file their own",
        "basis": "A dependent with $45,000 of wages must file their own federal and state return. The engine computes only the head and spouse's return. The output definitions name no return, tax unit or household, the prompt shows one 'Tax unit' block, and the request asks for quantities 'for this household' and says to assume filing when required. Careful readers split both ways (pa_123.md section 3).",
        "cells": [
            {
                "scenario_id": "scenario_123",
                "variable": STATE_TAX,
                "state": "PA",
                "corrected": 4451.561279296875,
                "value_source": "head and spouse return plus the child's own PA-40 ($1,381.50), verification/definition_conformance.json",
            },
            {
                "scenario_id": "scenario_123",
                "variable": FED_TAX,
                "state": "PA",
                "corrected": 8420.240234375,
                "value_source": "head and spouse return plus the child's own federal return ($3,220.00), verification/definition_conformance.json",
            },
            {
                "scenario_id": "scenario_093",
                "variable": STATE_TAX,
                "state": "MO",
                "corrected": None,
                "value_source": "head and spouse return plus the dependent's own MO-1040, verification/definition_conformance.json",
            },
            {
                "scenario_id": "scenario_093",
                "variable": FED_TAX,
                "state": "MO",
                "corrected": None,
                "value_source": "head and spouse return plus the dependent's own federal return ($3,220.00), verification/definition_conformance.json",
            },
        ],
    },
}


def frozen_references() -> dict[tuple[str, str], float]:
    with (RUN / "reference_outputs.csv").open() as handle:
        return {
            (row["scenario_id"], row["variable"]): float(row["value"])
            for row in csv.DictReader(handle)
        }


def excluded() -> set[tuple[str, str]]:
    record = json.loads((RUN / "reference_exclusions.json").read_text())
    return {(e["scenario_id"], e["variable"]) for e in record["exclusions"]}


def household_scope_values() -> dict[tuple[str, str], float]:
    """Reference plus the dependent's own return, from the conformance scan."""
    scan = json.loads((HERE / "verification/definition_conformance.json").read_text())
    frozen = frozen_references()
    values = {}
    for row in scan["household_scope_records"]:
        for output in (STATE_TAX, FED_TAX):
            key = (row["scenario_id"], output)
            values[key] = frozen[key] + row["own_return"]["outputs"][output]
    return values


def main() -> None:
    frozen = frozen_references()
    already = excluded()
    scope = household_scope_values()
    out = {
        "schema_version": 1,
        "status": {
            "state": f"ruled {RULED}",
            "summary": (
                f"Proposed {DRAFTED}; Max ruled {RULED}. Under d1022 the next release "
                f"after {AFTER_RELEASE} installs every root cause's exclusion records "
                "(variant exclude_all in verification/leaderboard_impact.json), and the "
                "four CONFIRMED cells are regenerated once fixed policyengine-us versions "
                "land. Under d994 the same release excludes the two Louisiana cells this "
                "pass skipped. decided_on is the ruling's date, which is also the draft "
                "date; each record names its ruling in decision."
            ),
            "rulings": RULINGS,
            "not_ruled": (
                "The pass's own expectations, not part of either ruling: a reference "
                "regenerated on a fixed policyengine-us should reproduce its regeneration "
                "record's regenerated_value to within the $1 exact-match tolerance; and "
                "the upstream engine fixes are being opened separately, so each record's "
                "upstream still reads 'to be filed', as 24 engine-defect records of the "
                "published exclusion record do."
            ),
        },
        "rules": (
            "reference_audit/2026-09-28 rule 2 (a scored reference follows from the stated facts "
            "and from law published before the 2026-07-03 freeze) and rule 4 (an output whose "
            "reference turns on a fact the prompt does not state is excluded)."
        ),
        "root_causes": {},
    }
    for cause, spec in ROOT_CAUSES.items():
        exclusions, regenerations = [], []
        for cell in spec["cells"]:
            key = (cell["scenario_id"], cell["variable"])
            if key in already:
                raise SystemExit(f"{key} is already excluded")
            value = cell["corrected"]
            if value is None:
                value = scope[key]
            elif key in scope and abs(scope[key] - value) > 0.01:
                raise SystemExit(f"{key}: {value} != conformance scan {scope[key]}")
            record = {
                "scenario_id": cell["scenario_id"],
                "variable": cell["variable"],
                "frozen_value": frozen[key],
                "alternative_value": value,
                "engine_version": ENGINE,
                "decided_on": DRAFTED,
                "decided_by": "developer",
                "decision": "d1022",
                "law": spec["law"],
                "note": (
                    "Found 2026-10-05 by the reference adversary (runs/claude/cases/"
                    f"us__{cell['scenario_id']}__{cell['variable']}) and verified "
                    f"independently on {DRAFTED} ({spec['evidence']}). "
                    f"Alternative value: {cell['value_source']}."
                ),
            }
            if spec["verdict"] == "CONFIRMED":
                record = {
                    **record,
                    "reason_code": "reference_engine_defect",
                    "root_cause": cause,
                    "alternative_reading": spec["basis"],
                    "defect": spec["defect"],
                    "upstream": UPSTREAM[cause],
                }
                regenerations.append(
                    {
                        "scenario_id": cell["scenario_id"],
                        "variable": cell["variable"],
                        "state": cell["state"],
                        "frozen_value": frozen[key],
                        "regenerated_value": value,
                        "cause": cause,
                        "basis": spec["basis"],
                        "law": spec["law"],
                        "engine_version": ENGINE,
                        "value_source": cell["value_source"],
                        "upstream": UPSTREAM[cause],
                        "decision": "d1022",
                    }
                )
            else:
                record = {
                    **record,
                    "reason_code": "reference_depends_on_unlisted_input",
                    "root_cause": cause,
                    "unlisted_input": spec["unlisted_input"],
                    "alternative_reading": spec["basis"],
                }
            exclusions.append(record)
        out["root_causes"][cause] = {
            "verdict": spec["verdict"],
            "evidence": spec["evidence"],
            "exclusions": exclusions,
            "regenerations": regenerations,
        }
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
