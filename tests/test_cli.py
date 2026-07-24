from __future__ import annotations

import json
from pathlib import Path

from plasmid_oracle import DatabaseSetupResult
from plasmid_oracle.cli import main


def test_cli_annotates_a_raw_sequence_as_json(capsys) -> None:
    exit_code = main(
        [
            "annotate",
            "--sequence",
            "ATGCCGTAGCTAATGCCGTAGCTA",
            "--mode",
            "fast",
            "--format",
            "json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["sequence"]["length"] == 24
    assert output["analysis"]["provider_runs"][0]["name"] == "pyrodigal"


def test_cli_prints_a_readable_report_by_default(capsys) -> None:
    exit_code = main(
        [
            "annotate",
            "--sequence",
            "ATGCCGTAGCTAATGCCGTAGCTA",
            "--mode",
            "fast",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "24 bp" in output
    assert "resolved annotations" in output
    assert "Providers" in output
    assert "pyrodigal: completed" in output


def test_cli_file_output_defaults_to_json(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "result.json"

    exit_code = main(
        [
            "annotate",
            "--sequence",
            "ATGCCGTAGCTAATGCCGTAGCTA",
            "--mode",
            "fast",
            "--output",
            str(output_path),
        ]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == ""
    assert json.loads(output_path.read_text(encoding="utf-8"))["schema_version"] == "3"


def test_cli_batch_writes_jsonl_summary(tmp_path: Path, capsys) -> None:
    input_path = tmp_path / "batch.jsonl"
    output_path = tmp_path / "batch.out.jsonl"
    input_path.write_text(
        json.dumps({"id": "p1", "sequence": "ATGCCGTAGCTAATGCCGTAGCTA"}) + "\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "batch",
            "--input",
            str(input_path),
            "--output",
            str(output_path),
            "--mode",
            "fast",
            "--no-cache",
            "--json",
        ]
    )

    summary = json.loads(capsys.readouterr().out)
    output = [
        json.loads(line)
        for line in output_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert exit_code == 0
    assert summary["completed_records"] == 1
    assert output[-1]["record_type"] == "manifest"


def test_cli_doctor_reports_machine_readable_status(capsys) -> None:
    exit_code = main(["doctor", "--mode", "fast", "--json"])

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert output["ready"] is True
    assert output["providers"][0]["name"] == "pyrodigal"


def test_cli_setup_dispatches_an_explicit_database_install(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    database_dir = tmp_path / "mob"
    received: dict[str, object] = {}

    def fake_setup(component: str, **kwargs: object) -> DatabaseSetupResult:
        received["component"] = component
        received.update(kwargs)
        return DatabaseSetupResult(
            component="mob_suite",
            path=database_dir,
            detail="MOB-suite database initialized",
        )

    monkeypatch.setattr("plasmid_oracle.cli.setup_database", fake_setup)

    exit_code = main(
        [
            "setup",
            "mob-suite",
            "--mob-database",
            str(database_dir),
            "--force",
            "--timeout",
            "1200",
            "--json",
        ]
    )

    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert received == {
        "component": "mob-suite",
        "force": True,
        "mob_database_dir": database_dir,
        "timeout_seconds": 1200.0,
    }
    assert output == {
        "component": "mob_suite",
        "detail": "MOB-suite database initialized",
        "path": str(database_dir),
    }
