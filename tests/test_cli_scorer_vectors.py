"""Tests for the ``export-scorer-vectors`` CLI subcommand wiring."""

import json

from policybench.cli import main
from policybench.scorer_vectors import FIXTURE_VERSION


def test_cli_export_scorer_vectors_writes_fixture(tmp_path, monkeypatch, capsys):
    output = tmp_path / "scorer_vectors.json"
    monkeypatch.setattr(
        "sys.argv",
        ["policybench", "export-scorer-vectors", "-o", str(output)],
    )

    main()

    assert output.exists()
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["version"] == FIXTURE_VERSION
    assert len(payload["vectors"]) >= 24

    out = capsys.readouterr().out
    assert "Scorer parity vectors saved to" in out
    assert str(output) in out


def test_cli_export_scorer_vectors_seed_is_deterministic(tmp_path, monkeypatch):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    for destination in (first, second):
        monkeypatch.setattr(
            "sys.argv",
            [
                "policybench",
                "export-scorer-vectors",
                "-o",
                str(destination),
                "--seed",
                "7",
            ],
        )
        main()

    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")
