from __future__ import annotations

from dataclasses import dataclass, replace
from importlib.metadata import version
from typing import Literal, cast

import pyrodigal

from plasmid_oracle.model import (
    AbsenceSemantics,
    Annotation,
    AnnotationSource,
    EvidenceMetrics,
    Integrity,
    Location,
    ProviderCapability,
    SequenceInfo,
    Strand,
    Topology,
)
from plasmid_oracle.pipeline import (
    ProviderContext,
    ProviderDiagnostic,
    ProviderResult,
    ProviderSpec,
)

_ADAPTER_VERSION = "1"
_TOOL_VERSION = version("pyrodigal")
_AMBIGUOUS_DNA = str.maketrans({base: "N" for base in "RYSWKMBDHV"})
_VALID_TRANSLATION_TABLES = frozenset(
    {1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14, 15, 16, 21, 22, 23, 24, 25, 26, 29, 30, 32, 33}
)
TranslationTable = Literal[
    1,
    2,
    3,
    4,
    5,
    6,
    9,
    10,
    11,
    12,
    13,
    14,
    15,
    16,
    21,
    22,
    23,
    24,
    25,
    26,
    29,
    30,
    32,
    33,
]


def _same_translation_end(left: Annotation, right: Annotation) -> bool:
    if left.location.strand is not right.location.strand:
        return False
    if left.location.strand is Strand.FORWARD:
        return left.location.end == right.location.end
    if left.location.strand is Strand.REVERSE:
        return left.location.start == right.location.start
    return False


def _is_suffix_duplicate(candidate: Annotation, other: Annotation) -> bool:
    candidate_sequence = candidate.nucleotide_sequence
    other_sequence = other.nucleotide_sequence
    return (
        candidate_sequence is not None
        and other_sequence is not None
        and len(candidate_sequence) < len(other_sequence)
        and _same_translation_end(candidate, other)
        and other_sequence.endswith(candidate_sequence)
    )


@dataclass(frozen=True, slots=True)
class PyrodigalProvider:
    min_gene: int = 90
    translation_table: int = 11

    spec = ProviderSpec(
        name="pyrodigal",
        version=_ADAPTER_VERSION,
        modes=("minimal", "fast", "standard", "deep"),
        capabilities=(
            ProviderCapability(
                concept="coding_sequence",
                absence_semantics=AbsenceSemantics.POSITIVE_ONLY,
                scope={"method": "ab initio gene_prediction"},
            ),
        ),
    )

    def __post_init__(self) -> None:
        if self.min_gene < 60:
            raise ValueError("Pyrodigal minimum gene length must be at least 60 nt")
        if self.translation_table not in _VALID_TRANSLATION_TABLES:
            raise ValueError("Unsupported Pyrodigal translation table")

    def run(
        self,
        sequence: SequenceInfo,
        context: ProviderContext,
    ) -> ProviderResult:
        del context
        query = sequence.bases.translate(_AMBIGUOUS_DNA)
        is_circular = sequence.topology is Topology.CIRCULAR
        if is_circular:
            query += query

        finder = pyrodigal.GeneFinder(
            meta=True,
            closed=is_circular,
            mask=sequence.ambiguous_base_count > 0,
            min_gene=self.min_gene,
            min_edge_gene=min(60, self.min_gene),
            max_overlap=min(60, self.min_gene),
        )
        genes = finder.find_genes(query)
        source = AnnotationSource(
            provider=self.spec.name,
            provider_version=self.spec.version,
            tool_version=_TOOL_VERSION,
        )

        normalized_genes: list[tuple[int, int, pyrodigal.Gene]] = []
        for gene in genes:
            start = int(gene.begin) - 1
            end = int(gene.end)
            if is_circular and start >= sequence.length:
                continue
            if end - start > sequence.length:
                continue
            normalized_genes.append((start, end, gene))

        normalized_genes.sort(key=lambda item: (item[0], item[1], int(item[2].strand)))
        annotations: list[Annotation] = []
        for index, (start, raw_end, gene) in enumerate(normalized_genes, start=1):
            end = raw_end
            if is_circular and end > sequence.length:
                end -= sequence.length

            strand = Strand.FORWARD if int(gene.strand) == 1 else Strand.REVERSE
            location = Location.from_bounds(
                start,
                end,
                sequence_length=sequence.length,
                topology=sequence.topology,
                strand=strand,
            )
            is_partial = bool(gene.partial_begin or gene.partial_end)
            annotations.append(
                Annotation(
                    annotation_id=f"pyrodigal:cds:{index}",
                    feature_type="CDS",
                    name="predicted CDS",
                    location=location,
                    source=source,
                    integrity=Integrity.PARTIAL if is_partial else Integrity.COMPLETE,
                    metrics=EvidenceMetrics(score=float(gene.score)),
                    nucleotide_sequence=str(gene.sequence()),
                    protein_sequence=str(
                        gene.translate(
                            translation_table=cast(
                                TranslationTable,
                                self.translation_table,
                            ),
                            include_stop=False,
                            strict=True,
                        )
                    ),
                    qualifiers={
                        "prediction_confidence": float(gene.confidence()) / 100,
                        "translation_table": self.translation_table,
                        "start_type": gene.start_type,
                        "rbs_motif": gene.rbs_motif,
                        "rbs_spacer": gene.rbs_spacer,
                        "partial_begin": bool(gene.partial_begin),
                        "partial_end": bool(gene.partial_end),
                    },
                )
            )

        if is_circular:
            annotations = [
                annotation
                for annotation in annotations
                if not any(
                    _is_suffix_duplicate(annotation, other)
                    for other in annotations
                    if other is not annotation
                )
            ]
            annotations = [
                replace(annotation, annotation_id=f"pyrodigal:cds:{index}")
                for index, annotation in enumerate(annotations, start=1)
            ]

        warnings: tuple[str, ...] = ()
        if sequence.ambiguous_base_count:
            warnings = ("Ambiguous IUPAC bases were passed to Pyrodigal as N",)
        return ProviderResult(
            annotations=tuple(annotations),
            tool_version=_TOOL_VERSION,
            warnings=warnings,
        )

    def diagnose(self, context: ProviderContext) -> ProviderDiagnostic:
        del context
        return ProviderDiagnostic(
            name=self.spec.name,
            available=True,
            provider_version=self.spec.version,
            tool_version=_TOOL_VERSION,
            capabilities=self.spec.capabilities,
        )
