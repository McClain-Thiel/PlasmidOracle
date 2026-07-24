from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from plasmid_oracle._immutability import freeze_mapping
from plasmid_oracle.model.annotation import AnnotationSource


@dataclass(frozen=True, slots=True)
class CharacterizationCall:
    name: str
    source: AnnotationSource
    confidence: float | None = None
    qualifiers: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Characterization call name cannot be empty")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be a fraction between 0 and 1")
        object.__setattr__(self, "qualifiers", freeze_mapping(self.qualifiers))


@dataclass(frozen=True, slots=True)
class QualityFlag:
    code: str
    message: str
    severity: str = "warning"
    source: AnnotationSource | None = None


@dataclass(frozen=True, slots=True)
class Characterization:
    replicons: tuple[CharacterizationCall, ...] = ()
    relaxases: tuple[CharacterizationCall, ...] = ()
    mpf_types: tuple[CharacterizationCall, ...] = ()
    orit_sites: tuple[CharacterizationCall, ...] = ()
    mobility: tuple[CharacterizationCall, ...] = ()
    host_range: tuple[CharacterizationCall, ...] = ()
    similarity_hits: tuple[CharacterizationCall, ...] = ()
    quality_flags: tuple[QualityFlag, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "replicons",
            "relaxases",
            "mpf_types",
            "orit_sites",
            "mobility",
            "host_range",
            "similarity_hits",
            "quality_flags",
        ):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))

    def merged_with(self, other: Characterization) -> Characterization:
        return Characterization(
            replicons=self.replicons + other.replicons,
            relaxases=self.relaxases + other.relaxases,
            mpf_types=self.mpf_types + other.mpf_types,
            orit_sites=self.orit_sites + other.orit_sites,
            mobility=self.mobility + other.mobility,
            host_range=self.host_range + other.host_range,
            similarity_hits=self.similarity_hits + other.similarity_hits,
            quality_flags=self.quality_flags + other.quality_flags,
        )
