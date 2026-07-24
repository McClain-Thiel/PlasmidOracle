from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from plasmid_oracle.errors import InvalidSerializedPlasmidError
from plasmid_oracle.model import (
    AnalysisManifest,
    Annotation,
    AnnotationSource,
    BiologicalConcept,
    BiologicalConceptType,
    Characterization,
    CharacterizationCall,
    DatabaseIdentity,
    EvidenceMetrics,
    Integrity,
    Location,
    Plasmid,
    ProviderCapability,
    ProviderRun,
    ProviderStatus,
    QualityFlag,
    ResolutionConflict,
    ResolutionStatus,
    ResolvedAnnotation,
    SequenceInfo,
    SequenceVariant,
    Span,
    Strand,
    VariantCoordinateSystem,
)
from plasmid_oracle.resolution import resolve_annotations

if TYPE_CHECKING:
    from plasmid_oracle.pipeline.provider import ProviderResult

SCHEMA_VERSION = "3"


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set | frozenset):
        return [_json_value(item) for item in value]
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"Value of type {type(value).__name__} is not JSON-compatible")


def _sequence_value(sequence: SequenceInfo) -> dict[str, Any]:
    payload = cast(dict[str, Any], _json_value(sequence))
    payload["length"] = sequence.length
    return payload


def _resolved_value(annotation: ResolvedAnnotation) -> dict[str, Any]:
    return {
        "annotation_id": annotation.annotation_id,
        "feature_type": annotation.feature_type,
        "name": annotation.name,
        "location": _json_value(annotation.location),
        "evidence_ids": [item.evidence_id for item in annotation.evidence],
        "status": annotation.status.value,
        "aliases": list(annotation.aliases),
        "canonical_ids": list(annotation.canonical_ids),
        "integrity": annotation.integrity.value,
        "conflicts": _json_value(annotation.conflicts),
        "nucleotide_sequence": annotation.nucleotide_sequence,
        "protein_sequence": annotation.protein_sequence,
    }


def to_dict(plasmid: Plasmid) -> dict[str, Any]:
    if not isinstance(plasmid, Plasmid):
        raise TypeError("to_dict expects a Plasmid")
    return {
        "schema_version": SCHEMA_VERSION,
        "sequence": _sequence_value(plasmid.sequence),
        "evidence": _json_value(plasmid.evidence),
        "annotations": [_resolved_value(annotation) for annotation in plasmid.annotations],
        "characterization": _json_value(plasmid.characterization),
        "source_metadata": _json_value(plasmid.source_metadata),
        "analysis": _json_value(plasmid.analysis),
    }


def to_json(
    plasmid: Plasmid,
    *,
    indent: int | None = 2,
) -> str:
    return json.dumps(
        to_dict(plasmid),
        indent=indent,
        sort_keys=True,
        allow_nan=False,
    )


def _mapping(value: object, *, context: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InvalidSerializedPlasmidError(f"{context} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise InvalidSerializedPlasmidError(f"{context} keys must be strings")
    return cast(Mapping[str, Any], value)


def _sequence_items(value: object, *, context: str) -> Sequence[Any]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise InvalidSerializedPlasmidError(f"{context} must be an array")
    return value


def _required(payload: Mapping[str, Any], key: str, *, context: str) -> Any:
    if key not in payload:
        raise InvalidSerializedPlasmidError(f"{context} is missing {key!r}")
    return payload[key]


def _string(value: object, *, context: str) -> str:
    if not isinstance(value, str):
        raise InvalidSerializedPlasmidError(f"{context} must be a string")
    return value


def _optional_string(value: object, *, context: str) -> str | None:
    if value is None:
        return None
    return _string(value, context=context)


def _number(value: object, *, context: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise InvalidSerializedPlasmidError(f"{context} must be a number")
    return float(value)


def _optional_number(value: object, *, context: str) -> float | None:
    if value is None:
        return None
    return _number(value, context=context)


def _optional_int(value: object, *, context: str) -> int | None:
    if value is None:
        return None
    return int(_number(value, context=context))


def _strings(value: object, *, context: str) -> tuple[str, ...]:
    return tuple(
        _string(item, context=f"{context} item") for item in _sequence_items(value, context=context)
    )


def _location(value: object, *, context: str) -> Location:
    payload = _mapping(value, context=context)
    spans = tuple(
        Span(
            start=int(
                _number(
                    _required(
                        span_payload := _mapping(item, context=f"{context}.spans item"),
                        "start",
                        context=f"{context}.spans item",
                    ),
                    context=f"{context}.spans.start",
                )
            ),
            end=int(
                _number(
                    _required(span_payload, "end", context=f"{context}.spans item"),
                    context=f"{context}.spans.end",
                )
            ),
        )
        for item in _sequence_items(
            _required(payload, "spans", context=context),
            context=f"{context}.spans",
        )
    )
    return Location(
        spans=spans,
        sequence_length=int(
            _number(
                _required(payload, "sequence_length", context=context),
                context=f"{context}.sequence_length",
            )
        ),
        strand=Strand(
            _string(
                _required(payload, "strand", context=context),
                context=f"{context}.strand",
            )
        ),
    )


def _source(value: object, *, context: str) -> AnnotationSource:
    payload = _mapping(value, context=context)
    return AnnotationSource(
        provider=_string(
            _required(payload, "provider", context=context),
            context=f"{context}.provider",
        ),
        provider_version=_optional_string(
            payload.get("provider_version"),
            context=f"{context}.provider_version",
        ),
        tool_version=_optional_string(
            payload.get("tool_version"),
            context=f"{context}.tool_version",
        ),
        database=_optional_string(payload.get("database"), context=f"{context}.database"),
        database_version=_optional_string(
            payload.get("database_version"),
            context=f"{context}.database_version",
        ),
    )


def _concept(value: object, *, context: str) -> BiologicalConcept:
    payload = _mapping(value, context=context)
    return BiologicalConcept(
        concept_type=BiologicalConceptType(
            _string(
                _required(payload, "concept_type", context=context),
                context=f"{context}.concept_type",
            )
        ),
        name=_string(_required(payload, "name", context=context), context=f"{context}.name"),
        canonical_id=_optional_string(
            payload.get("canonical_id"),
            context=f"{context}.canonical_id",
        ),
        aliases=_strings(payload.get("aliases", ()), context=f"{context}.aliases"),
        metadata=_mapping(payload.get("metadata", {}), context=f"{context}.metadata"),
    )


def _concepts(value: object, *, context: str) -> tuple[BiologicalConcept, ...]:
    return tuple(
        _concept(item, context=f"{context} item")
        for item in _sequence_items(value, context=context)
    )


def _variant(value: object, *, context: str) -> SequenceVariant:
    payload = _mapping(value, context=context)
    return SequenceVariant(
        canonical_notation=_string(
            _required(payload, "canonical_notation", context=context),
            context=f"{context}.canonical_notation",
        ),
        coordinate_system=VariantCoordinateSystem(
            _string(
                _required(payload, "coordinate_system", context=context),
                context=f"{context}.coordinate_system",
            )
        ),
        gene=_optional_string(payload.get("gene"), context=f"{context}.gene"),
        position=_optional_int(payload.get("position"), context=f"{context}.position"),
        reference_residue=_optional_string(
            payload.get("reference_residue"),
            context=f"{context}.reference_residue",
        ),
        alternate_residue=_optional_string(
            payload.get("alternate_residue"),
            context=f"{context}.alternate_residue",
        ),
        reference_nucleotide=_optional_string(
            payload.get("reference_nucleotide"),
            context=f"{context}.reference_nucleotide",
        ),
        alternate_nucleotide=_optional_string(
            payload.get("alternate_nucleotide"),
            context=f"{context}.alternate_nucleotide",
        ),
        metadata=_mapping(payload.get("metadata", {}), context=f"{context}.metadata"),
    )


def _variants(value: object, *, context: str) -> tuple[SequenceVariant, ...]:
    return tuple(
        _variant(item, context=f"{context} item")
        for item in _sequence_items(value, context=context)
    )


def _annotation(value: object, *, context: str) -> Annotation:
    payload = _mapping(value, context=context)
    metrics_payload = _mapping(payload.get("metrics", {}), context=f"{context}.metrics")
    return Annotation(
        annotation_id=_string(
            _required(payload, "annotation_id", context=context),
            context=f"{context}.annotation_id",
        ),
        feature_type=_string(
            _required(payload, "feature_type", context=context),
            context=f"{context}.feature_type",
        ),
        name=_string(
            _required(payload, "name", context=context),
            context=f"{context}.name",
        ),
        location=_location(
            _required(payload, "location", context=context),
            context=f"{context}.location",
        ),
        source=_source(
            _required(payload, "source", context=context),
            context=f"{context}.source",
        ),
        canonical_ids=_strings(
            payload.get("canonical_ids", ()),
            context=f"{context}.canonical_ids",
        ),
        integrity=Integrity(
            _string(payload.get("integrity", "unknown"), context=f"{context}.integrity")
        ),
        metrics=EvidenceMetrics(
            identity=_optional_number(
                metrics_payload.get("identity"),
                context=f"{context}.metrics.identity",
            ),
            coverage=_optional_number(
                metrics_payload.get("coverage"),
                context=f"{context}.metrics.coverage",
            ),
            score=_optional_number(
                metrics_payload.get("score"),
                context=f"{context}.metrics.score",
            ),
            evalue=_optional_number(
                metrics_payload.get("evalue"),
                context=f"{context}.metrics.evalue",
            ),
        ),
        nucleotide_sequence=_optional_string(
            payload.get("nucleotide_sequence"),
            context=f"{context}.nucleotide_sequence",
        ),
        protein_sequence=_optional_string(
            payload.get("protein_sequence"),
            context=f"{context}.protein_sequence",
        ),
        qualifiers=_mapping(payload.get("qualifiers", {}), context=f"{context}.qualifiers"),
        concepts=_concepts(payload.get("concepts", ()), context=f"{context}.concepts"),
        variants=_variants(payload.get("variants", ()), context=f"{context}.variants"),
        evidence_id=_optional_string(
            payload.get("evidence_id"),
            context=f"{context}.evidence_id",
        )
        or "",
    )


def _call(value: object, *, context: str) -> CharacterizationCall:
    payload = _mapping(value, context=context)
    return CharacterizationCall(
        name=_string(_required(payload, "name", context=context), context=f"{context}.name"),
        source=_source(
            _required(payload, "source", context=context),
            context=f"{context}.source",
        ),
        confidence=_optional_number(
            payload.get("confidence"),
            context=f"{context}.confidence",
        ),
        qualifiers=_mapping(payload.get("qualifiers", {}), context=f"{context}.qualifiers"),
        concepts=_concepts(payload.get("concepts", ()), context=f"{context}.concepts"),
        evidence_id=_optional_string(
            payload.get("evidence_id"),
            context=f"{context}.evidence_id",
        )
        or "",
    )


def _calls(
    payload: Mapping[str, Any],
    key: str,
    *,
    context: str,
) -> tuple[CharacterizationCall, ...]:
    return tuple(
        _call(item, context=f"{context}.{key} item")
        for item in _sequence_items(payload.get(key, ()), context=f"{context}.{key}")
    )


def _characterization(value: object) -> Characterization:
    payload = _mapping(value, context="characterization")
    quality_flags: list[QualityFlag] = []
    for item in _sequence_items(
        payload.get("quality_flags", ()),
        context="characterization.quality_flags",
    ):
        flag = _mapping(item, context="characterization.quality_flags item")
        source_value = flag.get("source")
        quality_flags.append(
            QualityFlag(
                code=_string(
                    _required(flag, "code", context="quality flag"),
                    context="quality flag.code",
                ),
                message=_string(
                    _required(flag, "message", context="quality flag"),
                    context="quality flag.message",
                ),
                severity=_string(flag.get("severity", "warning"), context="quality flag.severity"),
                source=(
                    _source(source_value, context="quality flag.source")
                    if source_value is not None
                    else None
                ),
                evidence_id=_optional_string(
                    flag.get("evidence_id"),
                    context="quality flag.evidence_id",
                )
                or "",
            )
        )
    return Characterization(
        replicons=_calls(payload, "replicons", context="characterization"),
        relaxases=_calls(payload, "relaxases", context="characterization"),
        mpf_types=_calls(payload, "mpf_types", context="characterization"),
        orit_sites=_calls(payload, "orit_sites", context="characterization"),
        mobility=_calls(payload, "mobility", context="characterization"),
        host_range=_calls(payload, "host_range", context="characterization"),
        similarity_hits=_calls(payload, "similarity_hits", context="characterization"),
        quality_flags=tuple(quality_flags),
    )


def _database_identity(value: object, *, context: str) -> DatabaseIdentity:
    payload = _mapping(value, context=context)
    return DatabaseIdentity(
        database=_string(
            _required(payload, "database", context=context),
            context=f"{context}.database",
        ),
        version=_optional_string(payload.get("version"), context=f"{context}.version"),
        manifest_sha256=_optional_string(
            payload.get("manifest_sha256"),
            context=f"{context}.manifest_sha256",
        ),
        identity=_mapping(payload.get("identity", {}), context=f"{context}.identity"),
    )


def _database_identities(value: object, *, context: str) -> tuple[DatabaseIdentity, ...]:
    return tuple(
        _database_identity(item, context=f"{context} item")
        for item in _sequence_items(value, context=context)
    )


def _provider_capability(value: object, *, context: str) -> ProviderCapability:
    payload = _mapping(value, context=context)
    return ProviderCapability(
        concept=_string(
            _required(payload, "concept", context=context),
            context=f"{context}.concept",
        ),
        absence_semantics=_string(
            payload.get("absence_semantics", "positive_only"),
            context=f"{context}.absence_semantics",
        ),
        scope=_mapping(payload.get("scope", {}), context=f"{context}.scope"),
    )


def _provider_capabilities(value: object, *, context: str) -> tuple[ProviderCapability, ...]:
    return tuple(
        _provider_capability(item, context=f"{context} item")
        for item in _sequence_items(value, context=context)
    )


def _provider_run(value: object, *, context: str) -> ProviderRun:
    payload = _mapping(value, context=context)
    return ProviderRun(
        name=_string(_required(payload, "name", context=context), context=f"{context}.name"),
        status=ProviderStatus(
            _string(
                _required(payload, "status", context=context),
                context=f"{context}.status",
            )
        ),
        provider_version=_optional_string(
            payload.get("provider_version"),
            context=f"{context}.provider_version",
        ),
        tool_version=_optional_string(
            payload.get("tool_version"),
            context=f"{context}.tool_version",
        ),
        database_versions={
            key: _string(item, context=f"{context}.database_versions.{key}")
            for key, item in _mapping(
                payload.get("database_versions", {}),
                context=f"{context}.database_versions",
            ).items()
        },
        database_manifests=_database_identities(
            payload.get("database_manifests", ()),
            context=f"{context}.database_manifests",
        ),
        capabilities=_provider_capabilities(
            payload.get("capabilities", ()),
            context=f"{context}.capabilities",
        ),
        parameters=_mapping(payload.get("parameters", {}), context=f"{context}.parameters"),
        diagnostic_identity=_mapping(
            payload.get("diagnostic_identity", {}),
            context=f"{context}.diagnostic_identity",
        ),
        cache_key=_optional_string(payload.get("cache_key"), context=f"{context}.cache_key"),
        runtime_seconds=_number(
            payload.get("runtime_seconds", 0.0),
            context=f"{context}.runtime_seconds",
        ),
        warnings=_strings(payload.get("warnings", ()), context=f"{context}.warnings"),
        error=_optional_string(payload.get("error"), context=f"{context}.error"),
    )


def _analysis(value: object) -> AnalysisManifest:
    payload = _mapping(value, context="analysis")
    return AnalysisManifest(
        pipeline_version=_string(
            _required(payload, "pipeline_version", context="analysis"),
            context="analysis.pipeline_version",
        ),
        mode=_string(
            _required(payload, "mode", context="analysis"),
            context="analysis.mode",
        ),
        provider_runs=tuple(
            _provider_run(item, context="analysis.provider_runs item")
            for item in _sequence_items(
                payload.get("provider_runs", ()),
                context="analysis.provider_runs",
            )
        ),
        warnings=_strings(payload.get("warnings", ()), context="analysis.warnings"),
    )


def _sequence(value: object) -> SequenceInfo:
    payload = _mapping(value, context="sequence")
    sequence = SequenceInfo.from_raw(
        _string(
            _required(payload, "bases", context="sequence"),
            context="sequence.bases",
        ),
        topology=_string(
            _required(payload, "topology", context="sequence"),
            context="sequence.topology",
        ),
    )
    expected: tuple[tuple[str, object], ...] = (
        ("length", sequence.length),
        ("checksum", sequence.checksum),
        ("canonical_checksum", sequence.canonical_checksum),
        ("ambiguous_base_count", sequence.ambiguous_base_count),
    )
    for key, actual in expected:
        if key in payload and payload[key] != actual:
            raise InvalidSerializedPlasmidError(
                f"sequence.{key} does not match the normalized sequence"
            )
    return sequence


def _conflict(value: object, *, context: str) -> ResolutionConflict:
    payload = _mapping(value, context=context)
    return ResolutionConflict(
        code=_string(_required(payload, "code", context=context), context=f"{context}.code"),
        message=_string(
            _required(payload, "message", context=context),
            context=f"{context}.message",
        ),
        evidence_ids=_strings(
            _required(payload, "evidence_ids", context=context),
            context=f"{context}.evidence_ids",
        ),
    )


def _resolved(
    value: object,
    *,
    evidence_by_id: Mapping[str, Annotation],
    context: str,
) -> ResolvedAnnotation:
    payload = _mapping(value, context=context)
    evidence_ids = _strings(
        _required(payload, "evidence_ids", context=context),
        context=f"{context}.evidence_ids",
    )
    missing = tuple(identifier for identifier in evidence_ids if identifier not in evidence_by_id)
    if missing:
        rendered = ", ".join(repr(identifier) for identifier in missing)
        raise InvalidSerializedPlasmidError(f"{context} references missing evidence: {rendered}")
    return ResolvedAnnotation(
        annotation_id=_string(
            _required(payload, "annotation_id", context=context),
            context=f"{context}.annotation_id",
        ),
        feature_type=_string(
            _required(payload, "feature_type", context=context),
            context=f"{context}.feature_type",
        ),
        name=_string(_required(payload, "name", context=context), context=f"{context}.name"),
        location=_location(
            _required(payload, "location", context=context),
            context=f"{context}.location",
        ),
        evidence=tuple(evidence_by_id[identifier] for identifier in evidence_ids),
        status=ResolutionStatus(
            _string(
                _required(payload, "status", context=context),
                context=f"{context}.status",
            )
        ),
        aliases=_strings(payload.get("aliases", ()), context=f"{context}.aliases"),
        canonical_ids=_strings(
            payload.get("canonical_ids", ()),
            context=f"{context}.canonical_ids",
        ),
        integrity=Integrity(
            _string(payload.get("integrity", "unknown"), context=f"{context}.integrity")
        ),
        conflicts=tuple(
            _conflict(item, context=f"{context}.conflicts item")
            for item in _sequence_items(
                payload.get("conflicts", ()),
                context=f"{context}.conflicts",
            )
        ),
        nucleotide_sequence=_optional_string(
            payload.get("nucleotide_sequence"),
            context=f"{context}.nucleotide_sequence",
        ),
        protein_sequence=_optional_string(
            payload.get("protein_sequence"),
            context=f"{context}.protein_sequence",
        ),
    )


def _from_dict(value: Mapping[str, Any]) -> Plasmid:
    payload = _mapping(value, context="plasmid")
    version = _string(
        _required(payload, "schema_version", context="plasmid"),
        context="schema_version",
    )
    if version not in {"1", "2", SCHEMA_VERSION}:
        raise InvalidSerializedPlasmidError(
            f"Unsupported plasmid schema version {version!r}; expected 1, 2, or {SCHEMA_VERSION}"
        )

    sequence = _sequence(_required(payload, "sequence", context="plasmid"))
    evidence_key = "annotations" if version == "1" else "evidence"
    evidence = tuple(
        _annotation(item, context=f"{evidence_key} item")
        for item in _sequence_items(
            _required(payload, evidence_key, context="plasmid"),
            context=evidence_key,
        )
    )
    evidence_by_id = {item.evidence_id: item for item in evidence}
    if len(evidence_by_id) != len(evidence):
        raise InvalidSerializedPlasmidError("Evidence IDs must be unique")
    evidence_by_reference: dict[str, Annotation] = dict(evidence_by_id)
    for item in evidence:
        evidence_by_reference.setdefault(item.annotation_id, item)
    annotation_ids = {item.annotation_id for item in evidence}
    if len(annotation_ids) != len(evidence):
        raise InvalidSerializedPlasmidError("Evidence annotation IDs must be unique")

    annotations = (
        resolve_annotations(evidence)
        if version == "1"
        else tuple(
            _resolved(
                item,
                evidence_by_id=evidence_by_reference,
                context="annotations item",
            )
            for item in _sequence_items(
                _required(payload, "annotations", context="plasmid"),
                context="annotations",
            )
        )
    )
    return Plasmid(
        sequence=sequence,
        evidence=evidence,
        annotations=annotations,
        characterization=_characterization(
            _required(payload, "characterization", context="plasmid")
        ),
        source_metadata=_mapping(
            payload.get("source_metadata", {}),
            context="source_metadata",
        ),
        analysis=_analysis(_required(payload, "analysis", context="plasmid")),
    )


def from_dict(value: Mapping[str, Any]) -> Plasmid:
    try:
        return _from_dict(value)
    except InvalidSerializedPlasmidError:
        raise
    except (TypeError, ValueError) as error:
        raise InvalidSerializedPlasmidError(f"Invalid serialized plasmid: {error}") from error


def from_json(value: str) -> Plasmid:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError as error:
        raise InvalidSerializedPlasmidError(f"Invalid plasmid JSON: {error.msg}") from error
    return from_dict(_mapping(payload, context="plasmid"))


def provider_result_to_dict(result: ProviderResult) -> dict[str, Any]:
    return {
        "annotations": _json_value(result.annotations),
        "characterization": _json_value(result.characterization),
        "tool_version": result.tool_version,
        "database_versions": _json_value(result.database_versions),
        "database_manifests": _json_value(result.database_manifests),
        "warnings": list(result.warnings),
    }


def provider_result_from_dict(value: Mapping[str, Any]) -> ProviderResult:
    from plasmid_oracle.pipeline.provider import ProviderResult

    payload = _mapping(value, context="cached provider result")
    return ProviderResult(
        annotations=tuple(
            _annotation(item, context="cached provider annotation")
            for item in _sequence_items(
                payload.get("annotations", ()),
                context="cached provider annotations",
            )
        ),
        characterization=_characterization(payload.get("characterization", {})),
        tool_version=_optional_string(
            payload.get("tool_version"),
            context="cached provider result.tool_version",
        ),
        database_versions={
            key: _string(
                item,
                context=f"cached provider result.database_versions.{key}",
            )
            for key, item in _mapping(
                payload.get("database_versions", {}),
                context="cached provider result.database_versions",
            ).items()
        },
        database_manifests=_database_identities(
            payload.get("database_manifests", ()),
            context="cached provider result.database_manifests",
        ),
        warnings=_strings(
            payload.get("warnings", ()),
            context="cached provider result.warnings",
        ),
    )
