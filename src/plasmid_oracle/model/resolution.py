from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from plasmid_oracle.model.annotation import Annotation, Integrity
from plasmid_oracle.model.location import Location


class ResolutionStatus(StrEnum):
    SUPPORTED = "supported"
    SINGLE_SOURCE = "single_source"
    CONFLICTED = "conflicted"


@dataclass(frozen=True, slots=True)
class ResolutionConflict:
    code: str
    message: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("Resolution conflict code cannot be empty")
        if not self.message.strip():
            raise ValueError("Resolution conflict message cannot be empty")
        if not self.evidence_ids:
            raise ValueError("Resolution conflict must reference evidence")
        object.__setattr__(self, "evidence_ids", tuple(sorted(set(self.evidence_ids))))


@dataclass(frozen=True, slots=True)
class ResolvedAnnotation:
    annotation_id: str
    feature_type: str
    name: str
    location: Location
    evidence: tuple[Annotation, ...]
    status: ResolutionStatus
    aliases: tuple[str, ...] = ()
    canonical_ids: tuple[str, ...] = ()
    integrity: Integrity = Integrity.UNKNOWN
    conflicts: tuple[ResolutionConflict, ...] = ()
    nucleotide_sequence: str | None = None
    protein_sequence: str | None = None

    def __post_init__(self) -> None:
        if not self.annotation_id.strip():
            raise ValueError("Resolved annotation ID cannot be empty")
        if not self.feature_type.strip():
            raise ValueError("Resolved feature type cannot be empty")
        if not self.name.strip():
            raise ValueError("Resolved annotation name cannot be empty")
        if not self.evidence:
            raise ValueError("Resolved annotation must contain supporting evidence")
        if any(
            item.location.sequence_length != self.location.sequence_length for item in self.evidence
        ):
            raise ValueError("Resolved annotation evidence refers to a different sequence")

        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "status", ResolutionStatus(self.status))
        object.__setattr__(self, "aliases", tuple(self.aliases))
        object.__setattr__(self, "canonical_ids", tuple(self.canonical_ids))
        object.__setattr__(self, "integrity", Integrity(self.integrity))
        object.__setattr__(self, "conflicts", tuple(self.conflicts))

    @property
    def providers(self) -> tuple[str, ...]:
        return tuple(sorted({item.source.provider for item in self.evidence}))

    @property
    def support_count(self) -> int:
        return len(self.providers)
