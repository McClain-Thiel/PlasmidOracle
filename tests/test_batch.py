from __future__ import annotations

import json
from pathlib import Path

import plasmid_oracle as po


def _records(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


def test_jsonl_batch_writes_terminal_records_and_manifest(tmp_path: Path) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    input_path.write_text(
        "\n".join(
            (
                json.dumps({"id": "ok", "sequence": "ATGCCGTAGCTA" * 2}),
                json.dumps({"id": "bad", "sequence": "ATGCX"}),
            )
        )
        + "\n",
        encoding="utf-8",
    )

    summary = po.annotate_jsonl(
        input_path=input_path,
        output_path=output_path,
        mode="fast",
        threads=1,
        cache=False,
    )

    documents = _records(output_path)
    assert summary.completed_records == 1
    assert summary.failed_records == 1
    assert documents[-1]["record_type"] == "manifest"
    assert documents[-1]["records_sha256"] == summary.records_sha256
    assert {item["status"] for item in documents[:-1]} == {"completed", "failed"}
    assert all("input_sha256" in item for item in documents[:-1])
    assert all("output_sha256" in item for item in documents[:-1])


def test_jsonl_batch_resume_skips_completed_records(tmp_path: Path) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    input_path.write_text(
        json.dumps({"id": "ok", "sequence": "ATGCCGTAGCTA" * 2}) + "\n",
        encoding="utf-8",
    )

    first = po.annotate_jsonl(
        input_path=input_path,
        output_path=output_path,
        mode="fast",
        threads=1,
        cache=False,
    )
    second = po.annotate_jsonl(
        input_path=input_path,
        output_path=output_path,
        mode="fast",
        threads=1,
        cache=False,
    )

    documents = _records(output_path)
    assert first.completed_records == 1
    assert second.skipped_records == 1
    assert [item["record_type"] for item in documents].count("manifest") == 1
    assert [item["record_type"] for item in documents].count("record") == 1
