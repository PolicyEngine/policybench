# Response Retry Artifacts

These artifacts preserve bounded full-response retry rounds for the May 2026
paper snapshot. A retry unit is a full `(country, model, scenario_id)` response.
Accepted retries replace every output row for that unit; partial retry responses
are rejected and the original rows remain in the merged file.

The canonical response contract requires a parsed numeric value and a nonempty
explanation for every requested output. These retry artifacts are preserved so
readers can inspect the original broken responses, retry attempts, accepted
replacements, and rejected retries.

Per country and round:

- `target_units.csv`: full responses selected for retry.
- `original_failed_responses.csv.gz`: original rows for those full responses.
- `retry_predictions.csv.gz`: raw retry rows returned by the models.
- `accepted_retry_units.csv`: full responses accepted into the merged output.
- `rejected_retry_units.csv`: full responses rejected and why.
- `accepted_retry_rows.csv.gz`: retry rows accepted into the merged output.
- `replaced_original_responses.csv.gz`: original rows replaced by accepted retries.
- `merged_predictions.csv.gz`: source predictions with accepted full retries applied.
- `retry_metadata.json`: source paths, hashes, model filters, and target counts.

Round 2 used the Round 1 merged predictions as its source and only targeted
models that had at least one accepted retry in Round 1.
