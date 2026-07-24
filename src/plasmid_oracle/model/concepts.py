from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from plasmid_oracle._immutability import freeze_mapping


class BiologicalConceptType(StrEnum):
    GENE = "gene"
    ALLELE = "allele"
    SEQUENCE_VARIANT = "sequence_variant"
    PROTEIN_TAG = "protein_tag"
    EPITOPE_TAG = "epitope_tag"
    PROMOTER = "promoter"
    ORIGIN = "origin"
    TERMINATOR = "terminator"
    RESISTANCE_MARKER = "resistance_marker"
    REPLICON = "replicon"
    RELAXASE = "relaxase"
    ORIT = "orit"
    MOBILITY = "mobility"
    HOST_RANGE = "host_range"
    SIMILARITY = "similarity"
    QUALITY_FLAG = "quality_flag"


class VariantCoordinateSystem(StrEnum):
    NUCLEOTIDE = "nucleotide"
    PROTEIN = "protein"


@dataclass(frozen=True, slots=True)
class BiologicalConcept:
    concept_type: BiologicalConceptType | str
    name: str
    canonical_id: str | None = None
    aliases: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Biological concept name cannot be empty")
        concept_type = BiologicalConceptType(self.concept_type)
        object.__setattr__(self, "concept_type", concept_type)
        object.__setattr__(self, "aliases", tuple(self.aliases))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class SequenceVariant:
    canonical_notation: str
    coordinate_system: VariantCoordinateSystem | str
    gene: str | None = None
    position: int | None = None
    reference_residue: str | None = None
    alternate_residue: str | None = None
    reference_nucleotide: str | None = None
    alternate_nucleotide: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.canonical_notation.strip():
            raise ValueError("Sequence variant notation cannot be empty")
        if self.position is not None and self.position < 1:
            raise ValueError("Sequence variant position must be one-based")
        object.__setattr__(
            self,
            "coordinate_system",
            VariantCoordinateSystem(self.coordinate_system),
        )
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))
