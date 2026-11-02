"""Compute named outputs, with the pinned conventions, on the policyengine-us
that PYTHONPATH puts first: probe_cells.py <label> <scenario_id>:<variable> ...

Used to find the upstream commit that fixes an excluded output, by running it
on a merge commit's checkout and on its first parent's
(evidence/upstream_bisect.md)."""
import io, sys
from pathlib import Path
PB = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PB / "reference_audit/2026-10-09-engine-upgrade/scripts"))
import build_references_upgrade as build
import pandas as pd
from policyengine_us import CountryTaxBenefitSystem
label, keys = sys.argv[1], [tuple(a.split(":")) for a in sys.argv[2:]]
base = build.load_base()
harness = build.load_module("h", build.HARNESS)
final = build.load_module("f", build.FIXES / "latest_final.py")
scen = pd.read_csv(io.StringIO(base.scenarios_csv))
vals = build.compute_items(CountryTaxBenefitSystem(reform=final.reform), scen, keys, harness.build_situation)
for k in keys: print(f"{label}\t{k[0]}\t{k[1]}\t{vals[k]!r}")
