# SNAP rounding parity (r13)

Executed the existing §2017(a) encoding for every household with a nonzero delta in the supplied r13 sweep, including scenario_118 below the $1 scoring threshold. The test covers each January–September 2026 month (FY2026). It does not test October–December FY2027 parameters or reproduce a full annual SNAP calculation from raw household facts.

**19 households, 171 monthly comparisons; 171/171 allotments match the rounding-only sandbox.**

The comparator runs the supplied r13 reform with `R13_COMPONENTS=round_min,round_allot`. The original annual SNAP calculation is asserted against the frozen sweep reference for each household. All other reforms and FY2027 parameter replacements are excluded from this comparison.

Axiom receives the household size and eligibility calculated by PolicyEngine, together with its floored net income. That floor is deliberately held constant: the original [PE contribution code](/Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/.venv-pe1755/lib/python3.13/site-packages/policyengine_us/variables/gov/usda/snap/snap_expected_contribution.py:20) and the sandbox both use it. The unmodified imported net-income module carries this boundary value through `snap_monthly_household_income` with all further deductions set to zero. This is a test of the allotment provision given net income, not a test of Axiom eligibility or deduction calculation. Every supplied boundary value is retained in `request.json` and `results.csv`.

The formulas round the allotment down and the small-household minimum to the nearest dollar at [2017/a.yaml:128](/Users/maxghenis/TheAxiomFoundation/rulespec-us/us/statutes/7/2017/a.yaml:128) and [2017/a.yaml:153](/Users/maxghenis/TheAxiomFoundation/rulespec-us/us/statutes/7/2017/a.yaml:153), consistent with [7 USC 2017(a)](https://www.law.cornell.edu/uscode/text/7/2017). The same rules also appear in the existing [7 CFR 273.10 encoding](/Users/maxghenis/TheAxiomFoundation/rulespec-us/us/regulations/7-cfr/273/10.yaml); that second module was read but not executed here.

All amounts below are monthly dollars. Each row represents nine separately executed months; the displayed amounts were checked identical across January–September. The original and corrected columns come from live PolicyEngine 1.755.4 simulations, not annual totals divided by 12.

| Household | State | PE minimum | Corrected minimum | Axiom minimum | PE allotment | Corrected allotment | Axiom allotment | Matches rounding law at tested boundary? |
|---|---|---:|---:|---:|---:|---:|---:|---|
| scenario_008 | NJ | 95.00 | 95.00 | 0.00 | 1,260.10 | 1,260.00 | 1,260.00 | Yes; federal minimum only* |
| scenario_012 | MS | 0.00 | 0.00 | 0.00 | 407.90 | 407.00 | 407.00 | Yes |
| scenario_023 | CA | 23.84 | 24.00 | 24.00 | 35.20 | 35.00 | 35.00 | Yes |
| scenario_027 | CT | 23.84 | 24.00 | 24.00 | 23.84 | 24.00 | 24.00 | Yes |
| scenario_030 | TX | 23.84 | 24.00 | 24.00 | 23.84 | 24.00 | 24.00 | Yes |
| scenario_038 | LA | 0.00 | 0.00 | 0.00 | 601.30 | 601.00 | 601.00 | Yes |
| scenario_043 | CO | 23.84 | 24.00 | 24.00 | 298.00 | 298.00 | 298.00 | Yes |
| scenario_045 | MI | 23.84 | 24.00 | 24.00 | 23.84 | 24.00 | 24.00 | Yes |
| scenario_054 | NC | 0.00 | 0.00 | 0.00 | 505.70 | 505.00 | 505.00 | Yes |
| scenario_057 | LA | 23.84 | 24.00 | 24.00 | 219.00 | 219.00 | 219.00 | Yes |
| scenario_066 | VA | 23.84 | 24.00 | 24.00 | 298.00 | 298.00 | 298.00 | Yes |
| scenario_073 | MI | 23.84 | 24.00 | 24.00 | 23.84 | 24.00 | 24.00 | Yes |
| scenario_079 | AZ | 23.84 | 24.00 | 24.00 | 198.90 | 198.00 | 198.00 | Yes |
| scenario_080 | PA | 23.84 | 24.00 | 24.00 | 298.00 | 298.00 | 298.00 | Yes |
| scenario_100 | MT | 0.00 | 0.00 | 0.00 | 713.90 | 713.00 | 713.00 | Yes |
| scenario_108 | WI | 23.84 | 24.00 | 24.00 | 23.84 | 24.00 | 24.00 | Yes |
| scenario_109 | FL | 0.00 | 0.00 | 0.00 | 661.30 | 661.00 | 661.00 | Yes |
| scenario_112 | TX | 23.84 | 24.00 | 24.00 | 23.84 | 24.00 | 24.00 | Yes |
| scenario_118 | NY | 23.84 | 24.00 | 24.00 | 239.80 | 239.00 | 239.00 | Yes |

*New Jersey has a $95 state minimum override in PE. The tested §2017(a) output is the federal minimum; it is not compared as if it implemented the NJ override. For scenario_008 the calculated allotment exceeds both minimums, so the allotment comparison remains meaningful.

No numerical Axiom defect was found in the tested rounding outputs. Households already at the maximum can match PE before the fix; including them ensures the whole affected r13 household set was tested. FY2027 COLA encodings were not found in the tracked SNAP policy inventory. They are a coverage gap; no FY2027 correctness result is claimed.

Additional validation: executed four existing §2017(a) companion fixtures and checked all 14 derived-output assertions; all passed. Three parameter-output expectations were skipped because the CLI query interface accepts derived outputs. Exact requests/responses and summary are in `companion_*.json`.

Reproduce:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 /Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/.venv-pe1755/bin/python snap/run.py
PYTHONDONTWRITEBYTECODE=1 /Users/maxghenis/PolicyEngine/policybench/results/local/adds202609/triage/.venv-pe1755/bin/python snap/check_companions.py
python3 snap/build_report.py
```

`python3 snap/run.py --replay` reruns only the Rust engine from the saved PolicyEngine checkpoint, without importing PolicyEngine. No RuleSpec is created or modified.
