from pathlib import Path

import pandas as pd

from scripts.export_full_run import load_predictions


def _write_predictions(path: Path, model: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "model": model,
                "scenario_id": "s001",
                "variable": "income_tax",
                "prediction": 1,
            }
        ]
    ).to_csv(path, index=False)


def test_load_predictions_prefers_by_model_outputs(tmp_path: Path) -> None:
    country_dir = tmp_path / "us"
    _write_predictions(country_dir / "predictions.csv", "last_model_only")
    _write_predictions(country_dir / "by_model" / "model_a.csv", "model_a")
    _write_predictions(country_dir / "by_model" / "model_b.csv", "model_b")

    predictions = load_predictions(country_dir)

    assert sorted(predictions["model"]) == ["model_a", "model_b"]
    written = pd.read_csv(country_dir / "predictions.csv")
    assert sorted(written["model"]) == ["model_a", "model_b"]


def test_load_predictions_falls_back_to_root_predictions(tmp_path: Path) -> None:
    country_dir = tmp_path / "us"
    _write_predictions(country_dir / "predictions.csv", "combined")

    predictions = load_predictions(country_dir)

    assert predictions["model"].tolist() == ["combined"]
