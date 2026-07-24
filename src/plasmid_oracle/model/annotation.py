from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from plasmid_oracle._immutability import freeze_mapping
from plasmid_oracle.model.location import Location


class Integrity(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    INTERRUPTED = "interrupted"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class AnnotationSource:
    provider: str
    provider_version: str | None = None
    tool_version: str | None = None
    database: str | None = None
    database_version: str | None = None

    def __post_init__(self) -> None:
        if not self.provider.strip():
            raise ValueError("Annotation provider cannot be empty")


@dataclass(frozen=True, slots=True)
class EvidenceMetrics:
    identity: float | None = None
    coverage: float | None = None
    score: float | None = None
    evalue: float | None = None

    def __post_init__(self) -> None:
        if self.identity is not None and not 0 <= self.identity <= 1:
            raise ValueError("identity must be a fraction between 0 and 1")
        if self.coverage is not None and not 0 <= self.coverage <= 1:
            raise ValueError("coverage must be a fraction between 0 and 1")
        if self.evalue is not None and self.evalue < 0:
            raise ValueError("evalue cannot be negative")


@dataclass(frozen=True, slots=True)
class Annotation:
    annotation_id: str
    feature_type: str
    name: str
    location: Location
    source: AnnotationSource
    canonical_ids: tuple[str, ...] = ()
    integrity: Integrity = Integrity.UNKNOWN
    metrics: EvidenceMetrics = field(default_factory=EvidenceMetrics)
    nucleotide_sequence: str | None = None
    protein_sequence: str | None = None
    qualifiers: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.annotation_id.strip():
            raise ValueError("Annotation ID cannot be empty")
        if not self.feature_type.strip():
            raise ValueError("Feature type cannot be empty")
        if not self.name.strip():
            raise ValueError("Annotation name cannot be empty")

        try:
            integrity = Integrity(self.integrity)
        except ValueError as error:
            raise ValueError(f"Unsupported annotation integrity: {self.integrity!r}") from error

        object.__setattr__(self, "canonical_ids", tuple(self.canonical_ids))
        object.__setattr__(self, "integrity", integrity)
        object.__setattr__(self, "qualifiers", freeze_mapping(self.qualifiers))
