"""Check an engine against the fix modules' pre-fix evidence, before it ships.

For each evidence item (reference_audit/2026-10-09-engine-upgrade/evidence/),
compute the output on the importable policyengine-us, with the pinned
conventions alone and with the item's fix modules after them, and report:

  lands   the engine is within $1 of the evidence's corrected value (a flag
          equals it), which a regeneration needs;
  inert   the modules move it by no more than $1 there: nothing is left to fix.

This is the builder's regeneration gate (build_references_upgrade.py,
regeneration_target) run early, so a policyengine-us pull request can be checked
before it merges. PYTHONPATH may put a policyengine-us checkout ahead of the
installed one; the engine is then labelled by --label, since the installed
package's version would misname it. Nothing is written; the exit code is 1 when
any checked item fails.

  PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 \\
    PYTHONPATH=<policyengine-us checkout>:<policybench checkout> \\
    <venv>/bin/python .../check_against_evidence.py \\
      --evidence reference_audit/2026-10-09-engine-upgrade/evidence/pe2.37.2.json \\
      --label "PR #10032 head abc1234" [--module r02_ira_219g_v2.py ...]
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import build_references_upgrade as build  # noqa: E402

TOL = 1.0


def main(argv: list[str] | None = None) -> int:
    import pandas as pd
    import policyengine_us
    from policyengine_us import CountryTaxBenefitSystem

    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument(
        "--module",
        action="append",
        default=[],
        help="check only items whose modules include this one (repeatable)",
    )
    parser.add_argument("--fixes-dir", default=str(build.FIXES))
    args = parser.parse_args(argv)

    path = build.ROOT / args.evidence
    doc = build.load_evidence({"path": args.evidence, "sha256": build.sha256(path)})
    items = [
        item
        for item in doc["items"]
        if not args.module or set(args.module) & set(item["modules"])
    ]
    if not items:
        raise build.Refusal("no evidence item uses the named modules")
    pins = build.audit_module_pins([m for item in items for m in item["modules"]])
    stale = sorted(m for m, pin in pins.items() if doc["modules"].get(m) != pin)
    if stale:
        raise build.Refusal(f"the evidence ran other bytes of {stale}")
    base = build.load_base()
    fixes_dir = Path(args.fixes_dir).resolve()
    build.fix_module_pins(base.meta, fixes_dir)
    build.harness_pin()
    harness = build.load_module("upgrade_sweep_harness", build.HARNESS)
    final = build.load_module(f"upgrade_{build.FIX_ENTRY}", fixes_dir / "latest_final.py")
    scenarios = pd.read_csv(io.StringIO(base.scenarios_csv))
    requests = [(build.key_of(item), tuple(item["modules"])) for item in items]
    plain = build.compute_items(
        CountryTaxBenefitSystem(reform=final.reform),
        scenarios,
        [k for k, _ in requests],
        harness.build_situation,
    )
    corrected = build.module_values_on(
        final, scenarios, requests, harness.build_situation
    )
    print(
        f"{args.label} (policyengine_us from {Path(policyengine_us.__file__).parent}) "
        f"against {doc['engine']} evidence"
    )
    failed = 0
    for item, (k, modules) in zip(items, requests):
        value, after = plain[k], corrected[(k, modules)]
        target = float(item["corrected_value"])
        lands = abs(value - target) <= TOL and not build.beyond(k[1], target, value)
        inert = abs(after - value) <= TOL and not build.beyond(k[1], value, after)
        failed += not (lands and inert)
        print(
            f"  {'PASS' if lands and inert else 'FAIL'} {k[0]} {k[1]:44s} "
            f"engine {value:>11.2f}  target {target:>11.2f}  "
            f"{'lands' if lands else 'MISSES by ' + format(value - target, '+.2f')}; "
            f"{'inert' if inert else 'modules still move it to ' + format(after, '.2f')}"
            f"  [{'+'.join(modules)}]"
        )
    print(f"{len(items) - failed} of {len(items)} pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
