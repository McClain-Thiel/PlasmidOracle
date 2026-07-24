from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterable, Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from time import perf_counter
from typing import Any

from plasmid_oracle.errors import PlasmidOracleError, ProviderExecutionError
from plasmid_oracle.model import ProviderRun, ProviderStatus, Topology
from plasmid_oracle.pipeline import PIPELINE_VERSION, AnnotationProvider
from plasmid_oracle.serialization import to_dict

_TERMINAL_STATUSES = frozenset({"completed", "partial", "failed"})


@dataclass(frozen=True, slots=True)
class BatchSummary:
    input_path: str
    output_path: str
    input_sha256: str
    records_sha256: str
    total_records: int
    completed_records: int
    partial_records: int
    failed_records: int
    skipped_records: int
    runtime_seconds: float
    parameters: Mapping[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "record_type": "manifest",
            "pipeline_version": PIPELINE_VERSION,
            "input_path": self.input_path,
            "output_path": self.output_path,
            "input_sha256": self.input_sha256,
            "records_sha256": self.records_sha256,
            "total_records": self.total_records,
            "completed_records": self.completed_records,
            "partial_records": self.partial_records,
            "failed_records": self.failed_records,
            "skipped_records": self.skipped_records,
            "runtime_seconds": self.runtime_seconds,
            "parameters": dict(self.parameters),
            "provider_batching": {
                "used": False,
                "reason": "No bundled provider currently exposes native batch execution",
            },
        }


@dataclass(frozen=True, slots=True)
class _InputRecord:
    line_number: int
    record_id: str
    payload: Mapping[str, Any] | None
    input_sha256: str
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _ResumeState:
    completed: Mapping[str, str]
    kept_records: int = 0
    dropped_stale_records: int = 0


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _digest(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_lines(path: Path, lines: Iterable[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            for line in lines:
                temporary.write(line)
                temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _verify_output_checksum(payload: Mapping[str, object], *, context: str) -> None:
    recorded_checksum = payload.get("output_sha256")
    if not isinstance(recorded_checksum, str):
        raise ValueError(f"{context} is missing output_sha256")
    normalized = dict(payload)
    del normalized["output_sha256"]
    actual_checksum = _digest(normalized)
    if actual_checksum != recorded_checksum:
        raise ValueError(f"{context} output_sha256 does not match the record content")


def _input_checksums(records: tuple[_InputRecord, ...]) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for record in records:
        existing = checksums.setdefault(record.record_id, record.input_sha256)
        if existing != record.input_sha256:
            raise ValueError(
                "Batch input record IDs must be unique for resume: "
                f"{record.record_id!r} has multiple input checksums"
            )
    return checksums


def _prepare_output(
    path: Path,
    *,
    resume: bool,
    input_checksums: Mapping[str, str],
) -> _ResumeState:
    if not resume or not path.exists():
        _atomic_write_lines(path, ())
        return _ResumeState(completed={})

    completed: dict[str, str] = {}
    kept_lines: list[str] = []
    dropped_stale_records = 0
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValueError(
                f"existing output JSONL line {line_number} is not valid JSON: {error.msg}"
            ) from error
        if not isinstance(payload, dict):
            raise ValueError(f"existing output JSONL line {line_number} must be an object")
        if payload.get("record_type") == "manifest":
            continue
        if payload.get("record_type") != "record":
            raise ValueError(
                f"existing output JSONL line {line_number} has unsupported record_type"
            )
        status = payload.get("status")
        record_id = payload.get("record_id")
        input_sha = payload.get("input_sha256")
        if not isinstance(record_id, str) or not record_id:
            raise ValueError(f"existing output JSONL line {line_number} is missing record_id")
        if not isinstance(input_sha, str):
            raise ValueError(f"existing output JSONL line {line_number} is missing input_sha256")
        if not isinstance(status, str) or status not in _TERMINAL_STATUSES:
            raise ValueError(f"existing output JSONL line {line_number} has non-terminal status")
        _verify_output_checksum(
            payload,
            context=f"existing output JSONL line {line_number}",
        )
        if input_checksums.get(record_id) != input_sha:
            dropped_stale_records += 1
            continue
        kept_lines.append(_canonical_json(payload))
        completed[record_id] = input_sha
    _atomic_write_lines(path, kept_lines)
    return _ResumeState(
        completed=completed,
        kept_records=len(kept_lines),
        dropped_stale_records=dropped_stale_records,
    )


def _record_documents(path: Path) -> list[dict[str, object]]:
    documents: list[dict[str, object]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise ValueError(f"output JSONL line {line_number} must be an object")
        if payload.get("record_type") == "record":
            documents.append(payload)
    return documents


def _read_input_records(path: Path) -> tuple[_InputRecord, ...]:
    records: list[_InputRecord] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as error:
            records.append(
                _InputRecord(
                    line_number=line_number,
                    record_id=f"line:{line_number}",
                    payload=None,
                    input_sha256=sha256(line.encode("utf-8")).hexdigest(),
                    error=f"Invalid JSON: {error.msg}",
                )
            )
            continue
        if not isinstance(payload, Mapping):
            records.append(
                _InputRecord(
                    line_number=line_number,
                    record_id=f"line:{line_number}",
                    payload=None,
                    input_sha256=_digest(payload),
                    error="JSONL record must be an object",
                )
            )
            continue
        record_id = payload.get("id")
        records.append(
            _InputRecord(
                line_number=line_number,
                record_id=str(record_id) if record_id is not None else f"line:{line_number}",
                payload=payload,
                input_sha256=_digest(payload),
            )
        )
    return tuple(records)


def _metadata(record: _InputRecord) -> Mapping[str, object]:
    assert record.payload is not None
    metadata_value = record.payload.get("source_metadata", {})
    if not isinstance(metadata_value, Mapping):
        raise ValueError("source_metadata must be an object when provided")
    metadata = {str(key): value for key, value in metadata_value.items()}
    metadata.setdefault("id", record.record_id)
    metadata.setdefault("batch_line", record.line_number)
    return metadata


def _provider_run_payload(run: ProviderRun) -> dict[str, object]:
    return {
        "name": run.name,
        "status": run.status.value,
        "provider_version": run.provider_version,
        "tool_version": run.tool_version,
        "database_versions": dict(run.database_versions),
        "database_manifests": [
            {
                "database": item.database,
                "version": item.version,
                "manifest_sha256": item.manifest_sha256,
                "identity": dict(item.identity),
            }
            for item in run.database_manifests
        ],
        "capabilities": [
            {
                "concept": capability.concept,
                "absence_semantics": str(capability.absence_semantics),
                "scope": dict(capability.scope),
            }
            for capability in run.capabilities
        ],
        "parameters": dict(run.parameters),
        "diagnostic_identity": dict(run.diagnostic_identity),
        "cache_key": run.cache_key,
        "runtime_seconds": run.runtime_seconds,
        "warnings": list(run.warnings),
        "error": run.error,
    }


def _record_with_checksum(payload: dict[str, object]) -> dict[str, object]:
    payload["output_sha256"] = _digest(payload)
    return payload


def _failed_record(
    record: _InputRecord,
    *,
    error: str,
    provider_runs: tuple[ProviderRun, ...] = (),
) -> dict[str, object]:
    payload: dict[str, object] = {
        "record_type": "record",
        "record_id": record.record_id,
        "line_number": record.line_number,
        "input_sha256": record.input_sha256,
        "status": "failed",
        "error": error,
        "analysis": {
            "pipeline_version": PIPELINE_VERSION,
            "provider_runs": [_provider_run_payload(run) for run in provider_runs],
        },
    }
    return _record_with_checksum(payload)


def _run_record(
    record: _InputRecord,
    *,
    default_topology: Topology | str,
    mode: str,
    providers: tuple[AnnotationProvider, ...] | None,
    strict: bool,
    threads: int,
    timeout_seconds: float,
    cache: bool,
    cache_dir: Path | None,
    provider_workers: int,
) -> dict[str, object]:
    if record.error is not None:
        return _failed_record(record, error=record.error)
    assert record.payload is not None
    sequence = record.payload.get("sequence", record.payload.get("seq"))
    if not isinstance(sequence, str) or not sequence.strip():
        return _failed_record(record, error="Record must contain a non-empty sequence or seq field")
    topology = record.payload.get("topology", default_topology)
    if not isinstance(topology, str):
        return _failed_record(record, error="Record topology must be a string when provided")

    try:
        from plasmid_oracle.api import annotate

        plasmid = annotate(
            seq=sequence,
            topology=topology,
            mode=mode,
            providers=providers,
            source_metadata=_metadata(record),
            strict=strict,
            threads=threads,
            timeout_seconds=timeout_seconds,
            cache=cache,
            cache_dir=cache_dir,
            provider_workers=provider_workers,
        )
    except ProviderExecutionError as error:
        return _failed_record(
            record,
            error=str(error),
            provider_runs=tuple(error.provider_runs),
        )
    except (PlasmidOracleError, ValueError, OSError) as error:
        return _failed_record(record, error=str(error))

    incomplete = any(
        run.status not in {ProviderStatus.COMPLETED, ProviderStatus.CACHED}
        for run in plasmid.analysis.provider_runs
    )
    plasmid_payload = to_dict(plasmid)
    payload = {
        "record_type": "record",
        "record_id": record.record_id,
        "line_number": record.line_number,
        "input_sha256": record.input_sha256,
        "sequence_checksum": plasmid.sequence.checksum,
        "canonical_sequence_checksum": plasmid.sequence.canonical_checksum,
        "status": "partial" if incomplete else "completed",
        "result_sha256": _digest(plasmid_payload),
        "plasmid": plasmid_payload,
    }
    return _record_with_checksum(payload)


def annotate_jsonl(
    *,
    input_path: Path,
    output_path: Path,
    topology: Topology | str = Topology.CIRCULAR,
    mode: str = "minimal",
    providers: Iterable[AnnotationProvider] | None = None,
    strict: bool = True,
    threads: int = 1,
    timeout_seconds: float = 600.0,
    cache: bool = True,
    cache_dir: Path | None = None,
    provider_workers: int = 1,
    record_workers: int = 1,
    resume: bool = True,
) -> BatchSummary:
    if threads < 1:
        raise ValueError("threads must be at least 1")
    if provider_workers < 1:
        raise ValueError("provider_workers must be at least 1")
    if record_workers < 1:
        raise ValueError("record_workers must be at least 1")
    if record_workers > threads:
        raise ValueError("record_workers cannot exceed the total thread budget")

    started = perf_counter()
    input_path = input_path.expanduser()
    output_path = output_path.expanduser()
    input_sha256 = _file_sha256(input_path)
    records = _read_input_records(input_path)
    input_checksums = _input_checksums(records)
    resume_state = _prepare_output(
        output_path,
        resume=resume,
        input_checksums=input_checksums,
    )
    selected_providers = tuple(providers) if providers is not None else None

    pending = tuple(
        record
        for record in records
        if resume_state.completed.get(record.record_id) != record.input_sha256
    )
    worker_count = min(record_workers, max(1, len(pending)))
    record_threads = max(1, threads // worker_count)
    record_provider_workers = min(provider_workers, record_threads)

    with output_path.open("a", encoding="utf-8") as handle:
        if pending:
            with ThreadPoolExecutor(
                max_workers=worker_count,
                thread_name_prefix="plasmid-oracle-batch",
            ) as executor:
                futures = [
                    executor.submit(
                        _run_record,
                        record,
                        default_topology=topology,
                        mode=mode,
                        providers=selected_providers,
                        strict=strict,
                        threads=record_threads,
                        timeout_seconds=timeout_seconds,
                        cache=cache,
                        cache_dir=cache_dir,
                        provider_workers=record_provider_workers,
                    )
                    for record in pending
                ]
                for future in as_completed(futures):
                    payload = future.result()
                    handle.write(_canonical_json(payload))
                    handle.write("\n")
                    handle.flush()
                    os.fsync(handle.fileno())

        record_documents = _record_documents(output_path)
        statuses = [item.get("status") for item in record_documents]
        records_sha256 = _digest(record_documents)
        summary = BatchSummary(
            input_path=str(input_path),
            output_path=str(output_path),
            input_sha256=input_sha256,
            records_sha256=records_sha256,
            total_records=len(records),
            completed_records=sum(status == "completed" for status in statuses),
            partial_records=sum(status == "partial" for status in statuses),
            failed_records=sum(status == "failed" for status in statuses),
            skipped_records=len(records) - len(pending),
            runtime_seconds=perf_counter() - started,
            parameters={
                "mode": mode,
                "topology": Topology(topology).value,
                "strict": strict,
                "threads": threads,
                "record_workers": worker_count,
                "record_threads": record_threads,
                "provider_workers": record_provider_workers,
                "timeout_seconds": timeout_seconds,
                "cache": cache,
                "cache_dir": str(cache_dir) if cache_dir is not None else None,
                "resume": resume,
                "resumed_records": resume_state.kept_records,
                "dropped_stale_records": resume_state.dropped_stale_records,
            },
        )
        manifest = summary.to_dict()
        handle.write(_canonical_json(manifest))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    return summary
