from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def test_jsonl_batch_resume_reruns_changed_input_and_drops_stale_record(
    tmp_path: Path,
) -> None:
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
    old_record = next(item for item in _records(output_path) if item["record_type"] == "record")

    input_path.write_text(
        json.dumps({"id": "ok", "sequence": "ATGCCGTAGCTA" * 3}) + "\n",
        encoding="utf-8",
    )
    second = po.annotate_jsonl(
        input_path=input_path,
        output_path=output_path,
        mode="fast",
        threads=1,
        cache=False,
    )

    documents = _records(output_path)
    record_documents = [item for item in documents if item["record_type"] == "record"]
    manifest = documents[-1]
    assert first.completed_records == 1
    assert second.completed_records == 1
    assert second.skipped_records == 0
    assert len(record_documents) == 1
    assert record_documents[0]["input_sha256"] != old_record["input_sha256"]
    assert manifest["parameters"]["dropped_stale_records"] == 1


def test_jsonl_batch_resume_rejects_malformed_existing_output(tmp_path: Path) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    input_path.write_text(
        json.dumps({"id": "ok", "sequence": "ATGCCGTAGCTA" * 2}) + "\n",
        encoding="utf-8",
    )
    output_path.write_text("{not-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match="existing output JSONL line 1 is not valid JSON"):
        po.annotate_jsonl(
            input_path=input_path,
            output_path=output_path,
            mode="fast",
            threads=1,
            cache=False,
        )


def test_jsonl_batch_resume_rejects_tampered_existing_output(tmp_path: Path) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    input_path.write_text(
        json.dumps({"id": "ok", "sequence": "ATGCCGTAGCTA" * 2}) + "\n",
        encoding="utf-8",
    )
    po.annotate_jsonl(
        input_path=input_path,
        output_path=output_path,
        mode="fast",
        threads=1,
        cache=False,
    )
    documents = _records(output_path)
    documents[0]["status"] = "failed"
    output_path.write_text(
        "\n".join(json.dumps(document) for document in documents) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="output_sha256 does not match"):
        po.annotate_jsonl(
            input_path=input_path,
            output_path=output_path,
            mode="fast",
            threads=1,
            cache=False,
        )
