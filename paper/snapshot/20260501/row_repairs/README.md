# Row-level contract repairs

These artifacts preserve the final row-level repair pass applied after full-response retries and parser recovery. The repair pass targeted only rows still missing a parsed numeric value or non-empty explanation, retried the same model on the same household-output target, and accepted only rows with both a parsed numeric value and explanation. The final `merged_predictions.csv.gz` files have zero parse-contract failures.

The canonical manuscript snapshot uses the repaired country `predictions.csv.gz` files under `paper/snapshot/20260501/runs/`. The files here preserve the repair source predictions, reparsed source predictions, targets, attempts, accepted rows, replaced original rows, and merged outputs used to produce those canonical files.
