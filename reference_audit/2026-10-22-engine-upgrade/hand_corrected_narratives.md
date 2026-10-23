# Hand-corrected reference narratives

`hand_corrected_narratives.json` gives the reference narratives of the four outputs the
2026-10-22 engine upgrade changes. It is applied through
`scripts/narratives_upgrade.py --hand-corrected`, so the narrative writer (claude-haiku-4-5) is
not called. The 2026-10-12 upgrade's writer misstated the change behind six of its nine outputs.

Each text states figures from the 2.60.0 build's traces (`reference-build/reference_traces.json`).
`tests/test_build_references_upgrade_1022.py` checks each figure against the trace and
recomputes every sum the texts state. Each rule a text names is the one the upstream pull
request encodes, with its law: #10036 for California's MCE, and #10238 for the Pennsylvania and
Arkansas breakfast statutes.

The narratives these replace were stale:

- **scenario_031 SNAP.** The old text said the household's income "places it above the
  threshold for SNAP eligibility". On 2.60.0, California's MCE waives the net income test. The
  household is categorically eligible, and as a one-person household it gets the $24 minimum.
- **scenario_028 free school meals.** The old text predates the 2026-09-29 change that counts
  child support as school-meal income. It gave $60,010 of income and a 1.82 ratio, and said the
  household qualifies for reduced-price meals. The reference has counted the $1,267 of child
  support since then: $61,277, 1.86, the paid tier, as the household's reduced-price narrative
  already says.
- **scenario_117 and scenario_123 free school meals.** The old texts said the state does not
  offer universal free school meals. That is still true of lunch, but the households' K-12
  children now get a free breakfast, valued at $2.06 a school day ($2.90 less the $0.84 paid
  rate) over 180 days.
