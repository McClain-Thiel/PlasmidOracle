from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from statistics import median

from plasmid_oracle.model.annotation import Annotation, Integrity
from plasmid_oracle.model.location import Location, Span, Strand
from plasmid_oracle.model.resolution import (
    ResolutionConflict,
    ResolutionStatus,
    ResolvedAnnotation,
)

_CODING_FEATURE_TYPES = frozenset(
    {
        "antimicrobial_resistance_gene",
        "cds",
        "gene",
        "protein",
        "protein_match",
    }
)
_ANONYMOUS_NAMES = frozenset(
    {
        "cds",
        "hypothetical protein",
        "predicted cds",
        "predicted protein",
        "unknown",
        "unknown protein",
    }
)
_INTEGRITY_SEVERITY = {
    Integrity.COMPLETE: 0,
    Integrity.UNKNOWN: 1,
    Integrity.AMBIGUOUS: 2,
    Integrity.PARTIAL: 3,
    Integrity.INTERRUPTED: 4,
}
_NAME_TOKEN = re.compile(r"[^a-z0-9]+")


def _feature_family(feature_type: str) -> str:
    normalized = feature_type.strip().casefold()
    return "coding" if normalized in _CODING_FEATURE_TYPES else normalized


def _overlap(left: Location, right: Location) -> int:
    return sum(
        max(0, min(left_span.end, right_span.end) - max(left_span.start, right_span.start))
        for left_span in left.spans
        for right_span in right.spans
    )


def _is_contained_fragment(candidate: Annotation, other: Annotation) -> bool:
    if candidate.location.length >= other.location.length:
        return False
    if _feature_family(candidate.feature_type) != _feature_family(other.feature_type):
        return False
    if candidate.name.casefold() != other.name.casefold():
        return False
    candidate_strand = candidate.location.strand
    other_strand = other.location.strand
    if (
        candidate_strand is not Strand.UNKNOWN
        and other_strand is not Strand.UNKNOWN
        and candidate_strand is not other_strand
    ):
        return False
    incomplete = Integrity(candidate.integrity) in {
        Integrity.PARTIAL,
        Integrity.INTERRUPTED,
    }
    low_coverage = candidate.metrics.coverage is not None and candidate.metrics.coverage < 0.8
    return (
        (incomplete or low_coverage)
        and Integrity(other.integrity) is Integrity.COMPLETE
        and _overlap(candidate.location, other.location) / candidate.location.length >= 0.95
    )


def _normalized_name(value: str) -> str:
    return _NAME_TOKEN.sub("", value.casefold())


def _names_compatible(left: Annotation, right: Annotation) -> bool:
    if not (_specific_name(left) and _specific_name(right)):
        return False
    left_name = _normalized_name(left.name)
    right_name = _normalized_name(right.name)
    if not left_name or not right_name:
        return False
    return (
        left_name == right_name
        or (len(left_name) >= 4 and left_name in right_name)
        or (len(right_name) >= 4 and right_name in left_name)
    )


def _canonical_ids(annotation: Annotation) -> set[str]:
    identifiers = {identifier.casefold() for identifier in annotation.canonical_ids}
    identifiers.update(
        concept.canonical_id.casefold()
        for concept in annotation.concepts
        if concept.canonical_id is not None
    )
    return identifiers


def _sequences_compatible(left: Annotation, right: Annotation) -> bool:
    for left_sequence, right_sequence in (
        (left.protein_sequence, right.protein_sequence),
        (left.nucleotide_sequence, right.nucleotide_sequence),
    ):
        if left_sequence is None or right_sequence is None:
            continue
        left_normalized = left_sequence.casefold()
        right_normalized = right_sequence.casefold()
        if left_normalized == right_normalized:
            return True
        shorter, longer = sorted((left_normalized, right_normalized), key=len)
        if len(shorter) >= 30 and shorter in longer:
            return True
    return False


def _variants_compatible(left: Annotation, right: Annotation) -> bool:
    left_variants = {variant.canonical_notation.casefold() for variant in left.variants}
    right_variants = {variant.canonical_notation.casefold() for variant in right.variants}
    return bool(left_variants and right_variants and left_variants & right_variants)


def _coding_identity_signal(left: Annotation, right: Annotation) -> bool:
    left_ids = _canonical_ids(left)
    right_ids = _canonical_ids(right)
    return (
        bool(left_ids and right_ids and left_ids & right_ids)
        or _names_compatible(left, right)
        or _sequences_compatible(left, right)
        or _variants_compatible(left, right)
    )


def _compatible(left: Annotation, right: Annotation, *, threshold: float) -> bool:
    if left.location.sequence_length != right.location.sequence_length:
        return False
    left_family = _feature_family(left.feature_type)
    right_family = _feature_family(right.feature_type)
    if left_family != right_family:
        return False
    if _is_contained_fragment(left, right) or _is_contained_fragment(right, left):
        return True
    overlap = _overlap(left.location, right.location)
    coordinate_match = (
        overlap / left.location.length >= threshold and overlap / right.location.length >= threshold
    )
    if not coordinate_match:
        return False
    if left_family != "coding":
        return True
    return _coding_identity_signal(left, right)


def _evidence_sort_key(annotation: Annotation) -> tuple[object, ...]:
    return (
        annotation.location.start,
        annotation.location.end,
        _feature_family(annotation.feature_type),
        annotation.source.provider.casefold(),
        annotation.annotation_id,
        annotation.evidence_id,
    )


def _components(
    evidence: tuple[Annotation, ...],
    *,
    overlap_threshold: float,
) -> tuple[tuple[Annotation, ...], ...]:
    adjacency: list[set[int]] = [set() for _ in evidence]
    for left_index, left in enumerate(evidence):
        for right_index in range(left_index + 1, len(evidence)):
            if _compatible(left, evidence[right_index], threshold=overlap_threshold):
                adjacency[left_index].add(right_index)
                adjacency[right_index].add(left_index)

    components: list[tuple[Annotation, ...]] = []
    remaining = set(range(len(evidence)))
    while remaining:
        stack = [min(remaining)]
        indexes: set[int] = set()
        while stack:
            index = stack.pop()
            if index in indexes:
                continue
            indexes.add(index)
            remaining.discard(index)
            stack.extend(adjacency[index] - indexes)
        components.append(tuple(evidence[index] for index in sorted(indexes)))
    return tuple(components)


def _specific_name(annotation: Annotation) -> bool:
    return annotation.name.strip().casefold() not in _ANONYMOUS_NAMES


def _representative(cluster: tuple[Annotation, ...]) -> Annotation:
    def key(annotation: Annotation) -> tuple[object, ...]:
        metrics = annotation.metrics
        evidence_score = (metrics.identity or 0.0) * (metrics.coverage or 0.0)
        return (
            -int(annotation.feature_type.casefold() == "antimicrobial_resistance_gene"),
            -int(_specific_name(annotation)),
            -int(Integrity(annotation.integrity) is Integrity.COMPLETE),
            -len(annotation.canonical_ids),
            -evidence_score,
            annotation.name.casefold(),
            annotation.source.provider.casefold(),
            annotation.annotation_id,
        )

    return min(cluster, key=key)


def _location_signature(location: Location) -> tuple[tuple[int, int], ...]:
    return tuple((span.start, span.end) for span in location.spans)


def _consensus_spans(
    cluster: tuple[Annotation, ...],
    representative: Annotation,
) -> tuple[Span, ...]:
    counts = Counter(_location_signature(item.location) for item in cluster)
    highest = max(counts.values())
    candidates = {signature for signature, count in counts.items() if count == highest}
    representative_signature = _location_signature(representative.location)
    selected = (
        representative_signature if representative_signature in candidates else min(candidates)
    )
    return tuple(Span(start, end) for start, end in selected)


def _consensus_strand(
    cluster: tuple[Annotation, ...],
    representative: Annotation,
) -> Strand:
    known = [item.location.strand for item in cluster if item.location.strand is not Strand.UNKNOWN]
    if not known:
        return Strand.UNKNOWN
    counts = Counter(known)
    highest = max(counts.values())
    candidates = {strand for strand, count in counts.items() if count == highest}
    if representative.location.strand in candidates:
        return representative.location.strand
    return min(candidates, key=lambda strand: strand.value)


def _coordinate_conflict(cluster: tuple[Annotation, ...]) -> bool:
    if len({_location_signature(item.location) for item in cluster}) == 1:
        return False
    lengths = [item.location.length for item in cluster]
    allowed_difference = max(15, int(float(median(lengths)) * 0.05))
    starts = [item.location.start for item in cluster]
    ends = [item.location.end for item in cluster]
    wraps = {item.location.wraps_origin for item in cluster}
    return (
        max(starts) - min(starts) > allowed_difference
        or max(ends) - min(ends) > allowed_difference
        or len(wraps) > 1
    )


def _primary_evidence(cluster: tuple[Annotation, ...]) -> tuple[Annotation, ...]:
    primary = tuple(
        item
        for item in cluster
        if not any(_is_contained_fragment(item, other) for other in cluster if other is not item)
    )
    return primary or cluster


def _conflicts(cluster: tuple[Annotation, ...]) -> tuple[ResolutionConflict, ...]:
    evidence_ids = tuple(item.evidence_id for item in cluster)
    primary = _primary_evidence(cluster)
    conflicts: list[ResolutionConflict] = []
    strands = {
        item.location.strand for item in primary if item.location.strand is not Strand.UNKNOWN
    }
    if len(strands) > 1:
        conflicts.append(
            ResolutionConflict(
                code="strand_disagreement",
                message="Supporting evidence disagrees about feature strand",
                evidence_ids=evidence_ids,
            )
        )
    if _coordinate_conflict(primary):
        conflicts.append(
            ResolutionConflict(
                code="coordinate_disagreement",
                message="Supporting evidence disagrees materially about feature coordinates",
                evidence_ids=evidence_ids,
            )
        )
    integrities = {Integrity(item.integrity) for item in primary}
    if len(integrities) > 1:
        conflicts.append(
            ResolutionConflict(
                code="integrity_disagreement",
                message="Supporting evidence disagrees about feature completeness",
                evidence_ids=evidence_ids,
            )
        )
    return tuple(conflicts)


def _resolve_cluster(
    cluster: tuple[Annotation, ...],
    *,
    annotation_id: str,
) -> ResolvedAnnotation:
    ordered = tuple(sorted(cluster, key=_evidence_sort_key))
    representative = _representative(ordered)
    conflicts = _conflicts(ordered)
    providers = {item.source.provider for item in ordered}
    status = (
        ResolutionStatus.CONFLICTED
        if conflicts
        else ResolutionStatus.SUPPORTED
        if len(providers) > 1
        else ResolutionStatus.SINGLE_SOURCE
    )
    names = {
        item.name.strip()
        for item in ordered
        if _specific_name(item) and item.name.casefold() != representative.name.casefold()
    }
    canonical_ids = {canonical_id for item in ordered for canonical_id in item.canonical_ids}
    canonical_ids.update(
        concept.canonical_id
        for item in ordered
        for concept in item.concepts
        if concept.canonical_id is not None
    )
    primary = _primary_evidence(ordered)
    integrity = max(
        (Integrity(item.integrity) for item in primary),
        key=lambda item: _INTEGRITY_SEVERITY[item],
    )
    location = Location(
        spans=_consensus_spans(ordered, representative),
        sequence_length=representative.location.sequence_length,
        strand=_consensus_strand(ordered, representative),
    )
    feature_type = (
        "antimicrobial_resistance_gene"
        if any(item.feature_type.casefold() == "antimicrobial_resistance_gene" for item in ordered)
        else representative.feature_type
    )
    return ResolvedAnnotation(
        annotation_id=annotation_id,
        feature_type=feature_type,
        name=representative.name,
        location=location,
        evidence=ordered,
        status=status,
        aliases=tuple(sorted(names, key=str.casefold)),
        canonical_ids=tuple(sorted(canonical_ids)),
        integrity=integrity,
        conflicts=conflicts,
        nucleotide_sequence=representative.nucleotide_sequence,
        protein_sequence=representative.protein_sequence,
    )


def resolve_annotations(
    evidence: Iterable[Annotation],
    *,
    overlap_threshold: float = 0.8,
) -> tuple[ResolvedAnnotation, ...]:
    if not 0 < overlap_threshold <= 1:
        raise ValueError("overlap_threshold must be greater than zero and at most one")
    normalized = tuple(sorted(evidence, key=_evidence_sort_key))
    if not normalized:
        return ()
    if not all(isinstance(item, Annotation) for item in normalized):
        raise TypeError("resolve_annotations expects Annotation evidence")

    components = _components(normalized, overlap_threshold=overlap_threshold)
    ordered_components = tuple(
        sorted(
            components,
            key=lambda component: min(_evidence_sort_key(item) for item in component),
        )
    )
    return tuple(
        _resolve_cluster(component, annotation_id=f"resolved:{index:04d}")
        for index, component in enumerate(ordered_components, start=1)
    )
