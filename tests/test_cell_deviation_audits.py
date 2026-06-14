import json
import random
import sys
from pathlib import Path

import pandas as pd
import pytest

from policybench.cell_deviation_audits import (
    build_cell_deviation_audit_run,
    extract_json_result,
    run_cell_deviation_audits,
)
from policybench.scenarios import Person, Scenario, scenario_manifest


def _write_tiny_run(run_dir: Path) -> None:
    country_dir = run_dir / "us"
    country_dir.mkdir(parents=True)
    scenario = Scenario(
        id="scenario_000",
        country="us",
        state="CA",
        filing_status="single",
        adults=[Person(name="head", age=35, employment_income=50_000.0)],
        year=2026,
    )
    scenario_manifest([scenario]).to_csv(country_dir / "scenarios.csv", index=False)
    pd.DataFrame(
        [
            {
                "scenario_id": "scenario_000",
                "variable": "payroll_tax",
                "value": 1000.0,
                "impact_weight": None,
            }
        ]
    ).to_csv(country_dir / "reference_outputs.csv", index=False)
    by_model = country_dir / "by_model"
    by_model.mkdir()
    pd.DataFrame(
        [
            {
                "call_id": "model_a:scenario_000",
                "model": "model_a",
                "scenario_id": "scenario_000",
                "variable": "payroll_tax",
                "prediction": 1000.0,
                "explanation": "Correct. value = 1000",
                "raw_response": "{}",
            }
        ]
    ).to_csv(by_model / "model_a.csv", index=False)
    pd.DataFrame(
        [
            {
                "call_id": "model_b:scenario_000",
                "model": "model_b",
                "scenario_id": "scenario_000",
                "variable": "payroll_tax",
                "prediction": 700.0,
                "explanation": "Used the wrong tax base. value = 700",
                "raw_response": "{}",
            }
        ]
    ).to_csv(by_model / "model_b.csv", index=False)


def test_build_cell_deviation_audit_run_writes_grouped_packets(tmp_path: Path) -> None:
    run_dir = tmp_path / "full_run"
    audit_dir = tmp_path / "audits"
    _write_tiny_run(run_dir)

    manifest = build_cell_deviation_audit_run(
        run_dir=run_dir,
        output_dir=audit_dir,
        countries=["us"],
    )

    queue = json.loads((audit_dir / "queue.json").read_text())
    packet = json.loads(Path(queue[0]["packet_path"]).read_text())

    assert manifest["total_queued_cells"] == 1
    assert queue[0]["id"] == "us:scenario_000:payroll_tax"
    assert queue[0]["wrong_count"] == 1
    assert queue[0]["parsed_count"] == 2
    assert queue[0]["exact_count"] == 1
    assert packet["reference_value"] == 1000.0
    assert {row["model"] for row in packet["model_responses"]} == {
        "model_a",
        "model_b",
    }
    assert (
        "Provide the following policy quantities"
        in packet["scenario_summary"]["prompt"]["tool"]
    )
    assert (audit_dir / "cell_deviation_audit_result.schema.json").exists()


def test_extract_json_result_reads_fenced_json() -> None:
    result = extract_json_result(
        "```json\n"
        '{"id": "us:scenario_000:payroll_tax", "classification": "llm_error"}\n'
        "```"
    )

    assert result["classification"] == "llm_error"


def test_run_cell_deviation_audits_records_timing_with_fake_codex(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "full_run"
    audit_dir = tmp_path / "audits"
    _write_tiny_run(run_dir)
    build_cell_deviation_audit_run(
        run_dir=run_dir,
        output_dir=audit_dir,
        countries=["us"],
    )
    fake_codex = tmp_path / "fake_codex.py"
    fake_codex.write_text(
        f"""#!{sys.executable}
import json
import sys
from pathlib import Path

if sys.argv[1:3] == ["login", "status"]:
    print("Logged in using ChatGPT")
    raise SystemExit(0)

output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
result = {{
    "id": "us:scenario_000:payroll_tax",
    "classification": "llm_error",
    "confidence": 0.9,
    "summary": "Model B used the wrong payroll tax base.",
    "evidence": "Reference and model A agree at 1000.",
    "model_patterns": "model_a correct; model_b low",
    "arithmetic": "1000 - 700 = 300",
}}
output.write_text(json.dumps(result))
print(json.dumps({{"type": "agent_reasoning", "message": "fake"}}))
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)

    result = run_cell_deviation_audits(
        audit_dir=audit_dir,
        repo_dir=tmp_path,
        limit=1,
        codex_bin=str(fake_codex),
    )
    queue = json.loads((audit_dir / "queue.json").read_text())
    records = [
        json.loads(line)
        for line in (audit_dir / "audit_results.jsonl").read_text().splitlines()
    ]

    assert result.completed == 1
    assert result.failed == 0
    assert queue[0]["status"] == "complete"
    assert records[0]["classification"] == "llm_error"
    assert records[0]["elapsed_seconds"] >= 0
    assert Path(records[0]["raw_output_path"]).exists()
    assert records[0]["codex_events_path"] is None
    assert records[0]["stderr_path"] is None


def test_run_cell_deviation_audits_preflights_before_claiming_queue(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "full_run"
    audit_dir = tmp_path / "audits"
    _write_tiny_run(run_dir)
    build_cell_deviation_audit_run(
        run_dir=run_dir,
        output_dir=audit_dir,
        countries=["us"],
    )
    fake_codex = tmp_path / "fake_codex.py"
    fake_codex.write_text(
        f"""#!{sys.executable}
import sys

if sys.argv[1:3] == ["login", "status"]:
    print("invalid config", file=sys.stderr)
    raise SystemExit(1)

raise SystemExit("exec should not run")
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)

    with pytest.raises(RuntimeError, match="Codex preflight failed"):
        run_cell_deviation_audits(
            audit_dir=audit_dir,
            repo_dir=tmp_path,
            limit=1,
            codex_bin=str(fake_codex),
        )

    queue = json.loads((audit_dir / "queue.json").read_text())

    assert queue[0]["status"] == "queued"
    assert not (audit_dir / "audit_results.jsonl").read_text().strip()


def test_run_cell_deviation_audits_can_randomize_selection(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "full_run"
    audit_dir = tmp_path / "audits"
    _write_tiny_run(run_dir)
    build_cell_deviation_audit_run(
        run_dir=run_dir,
        output_dir=audit_dir,
        countries=["us"],
    )
    base_row = json.loads((audit_dir / "queue.json").read_text())[0]
    queue = []
    for suffix in ("a", "b", "c"):
        row = dict(base_row)
        row["id"] = f"us:scenario_000:payroll_tax_{suffix}"
        queue.append(row)
    (audit_dir / "queue.json").write_text(json.dumps(queue))

    fake_codex = tmp_path / "fake_codex.py"
    fake_codex.write_text(
        f"""#!{sys.executable}
import json
import sys
from pathlib import Path

if sys.argv[1:3] == ["login", "status"]:
    print("Logged in using ChatGPT")
    raise SystemExit(0)

output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
output.write_text(json.dumps({{
    "id": "placeholder",
    "classification": "llm_error",
    "confidence": 0.9,
    "summary": "ok",
    "evidence": "ok",
    "model_patterns": "ok",
    "arithmetic": "ok",
}}))
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)
    expected_order = [row["id"] for row in queue]
    random.Random(7).shuffle(expected_order)

    result = run_cell_deviation_audits(
        audit_dir=audit_dir,
        repo_dir=tmp_path,
        limit=1,
        codex_bin=str(fake_codex),
        randomize=True,
        random_seed=7,
    )
    records = [
        json.loads(line)
        for line in (audit_dir / "audit_results.jsonl").read_text().splitlines()
    ]

    assert result.completed == 1
    assert records[0]["id"] == expected_order[0]


def test_run_cell_deviation_audits_aborts_on_midbatch_environment_error(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "full_run"
    audit_dir = tmp_path / "audits"
    _write_tiny_run(run_dir)
    build_cell_deviation_audit_run(
        run_dir=run_dir,
        output_dir=audit_dir,
        countries=["us"],
    )
    base_row = json.loads((audit_dir / "queue.json").read_text())[0]
    queue = []
    for suffix in ("a", "b", "c"):
        row = dict(base_row)
        row["id"] = f"us:scenario_000:payroll_tax_{suffix}"
        queue.append(row)
    (audit_dir / "queue.json").write_text(json.dumps(queue))

    fake_codex = tmp_path / "fake_codex.py"
    fake_codex.write_text(
        f"""#!{sys.executable}
import sys
from pathlib import Path

if sys.argv[1:3] == ["login", "status"]:
    print("Logged in using ChatGPT")
    raise SystemExit(0)

output = Path(sys.argv[sys.argv.index("--output-last-message") + 1])
if output.name == ".codex_preflight_output.txt":
    output.write_text("OK")
    raise SystemExit(0)

print("Error loading config.toml: unknown variant `default`", file=sys.stderr)
raise SystemExit(1)
""",
        encoding="utf-8",
    )
    fake_codex.chmod(0o755)

    with pytest.raises(RuntimeError, match="Codex environment failure"):
        run_cell_deviation_audits(
            audit_dir=audit_dir,
            repo_dir=tmp_path,
            limit=3,
            parallel=1,
            codex_bin=str(fake_codex),
        )

    queue = json.loads((audit_dir / "queue.json").read_text())

    assert {row["status"] for row in queue} == {"queued"}
    assert not (audit_dir / "audit_results.jsonl").read_text().strip()
