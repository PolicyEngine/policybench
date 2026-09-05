"""Row-level scoring views the manuscript derives from a frozen country payload.

The published board scores each model on the outputs the release marks
``scored`` (every output except those ``reference_exclusions.json`` removes for
every model). The manuscript's alternative-view table (equal-output-group,
amount-only, positive-reference, zero-reference) must score the same rows, so
the flattening step that feeds it lives here, exclusion-aware and tested,
rather than inside the notebook.
"""

from __future__ import annotations

import pandas as pd

from policybench.analysis import score_single_prediction
from policybench.spec import metric_type_for_output, parse_person_output


def flatten_scored_predictions(country: str, country_payload: dict) -> pd.DataFrame:
    """One row per (scenario, output, model) with its 0-100 row score.

    Rows the payload marks ``scored: false`` are left out: they contribute to no
    model's published score and must not enter any manuscript view either.
    """
    rows = []
    for scenario_id, variables in country_payload["scenarioPredictions"].items():
        for variable, model_records in variables.items():
            parsed = parse_person_output(variable)
            output_group = parsed[1] if parsed else variable
            metric_type = metric_type_for_output(variable)
            for model, record in model_records.items():
                if record.get("scored") is False:
                    continue
                truth = record["groundTruth"]
                prediction = record["prediction"]
                rows.append(
                    {
                        "country": country,
                        "scenario_id": scenario_id,
                        "variable": variable,
                        "output_group": output_group,
                        "model": model,
                        "truth": truth,
                        "prediction": prediction,
                        "metric_type": metric_type,
                        "score": 100
                        * score_single_prediction(variable, truth, prediction),
                    }
                )
    return pd.DataFrame(
        rows,
        columns=[
            "country",
            "scenario_id",
            "variable",
            "output_group",
            "model",
            "truth",
            "prediction",
            "metric_type",
            "score",
        ],
    )


def country_scores_from_rows(frame: pd.DataFrame) -> pd.DataFrame:
    """Equal-output-group score per (country, model): mean over output groups
    of the mean row score within each group."""
    output_scores = (
        frame.groupby(["country", "model", "output_group"])["score"]
        .mean()
        .reset_index()
    )
    return output_scores.groupby(["country", "model"])["score"].mean().reset_index()
