from __future__ import annotations

import importlib
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from plasmid_oracle._immutability import freeze_mapping
from plasmid_oracle.model.annotation import Annotation
from plasmid_oracle.model.characterization import Characterization
from plasmid_oracle.model.manifest import AnalysisManifest, ProviderStatus
from plasmid_oracle.model.resolution import ResolutionConflict, ResolvedAnnotation
from plasmid_oracle.model.sequence import SequenceInfo


@dataclass(frozen=True, slots=True)
class Plasmid:
    sequence: SequenceInfo
    evidence: tuple[Annotation, ...] = ()
    annotations: tuple[ResolvedAnnotation, ...] = ()
    characterization: Characterization = field(default_factory=Characterization)
    source_metadata: Mapping[str, object] = field(default_factory=dict)
    analysis: AnalysisManifest = field(
        default_factory=lambda: AnalysisManifest(pipeline_version="unknown", mode="none")
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "annotations", tuple(self.annotations))
        object.__setattr__(self, "source_metadata", freeze_mapping(self.source_metadata))

    @property
    def amr_genes(self) -> tuple[ResolvedAnnotation, ...]:
        return self.features(feature_type="antimicrobial_resistance_gene")

    @property
    def conflicts(self) -> tuple[ResolutionConflict, ...]:
        return tuple(
            conflict for annotation in self.annotations for conflict in annotation.conflicts
        )

    @property
    def provider_status(self) -> Mapping[str, ProviderStatus]:
        return MappingProxyType({run.name: run.status for run in self.analysis.provider_runs})

    @property
    def analysis_complete(self) -> bool:
        runs = self.analysis.provider_runs
        return bool(runs) and all(
            run.status in {ProviderStatus.COMPLETED, ProviderStatus.CACHED} for run in runs
        )

    def features(
        self,
        *,
        feature_type: str | None = None,
        status: str | None = None,
    ) -> tuple[ResolvedAnnotation, ...]:
        normalized_type = feature_type.casefold() if feature_type is not None else None
        normalized_status = status.casefold() if status is not None else None
        return tuple(
            feature
            for feature in self.annotations
            if (normalized_type is None or feature.feature_type.casefold() == normalized_type)
            and (normalized_status is None or feature.status.value.casefold() == normalized_status)
        )

    def find(self, query: str) -> tuple[ResolvedAnnotation, ...]:
        needle = query.strip().casefold()
        if not needle:
            raise ValueError("Feature query cannot be empty")
        return tuple(
            feature
            for feature in self.annotations
            if needle in feature.name.casefold()
            or any(needle in alias.casefold() for alias in feature.aliases)
            or any(needle in identifier.casefold() for identifier in feature.canonical_ids)
        )

    def summary(self) -> str:
        from plasmid_oracle.reporting import render_text

        return render_text(self)

    def to_dataframe(self) -> Any:
        try:
            pandas = importlib.import_module("pandas")
        except ImportError as error:
            raise RuntimeError(
                "DataFrame export requires pandas; install plasmid-oracle[plannotate] "
                "or pandas directly"
            ) from error
        data_frame = getattr(pandas, "DataFrame", None)
        if data_frame is None:
            raise RuntimeError(
                "DataFrame export requires a complete pandas installation; "
                "install plasmid-oracle[plannotate] or pandas directly"
            )

        from plasmid_oracle.reporting import annotation_rows

        return data_frame(annotation_rows(self))

    def __str__(self) -> str:
        return self.summary()

    def __repr__(self) -> str:
        identifier = self.source_metadata.get("id")
        rendered_id = repr(identifier) if identifier is not None else "None"
        return (
            f"Plasmid(id={rendered_id}, length={self.sequence.length}, "
            f"topology={self.sequence.topology.value!r}, "
            f"annotations={len(self.annotations)}, evidence={len(self.evidence)}, "
            f"mode={self.analysis.mode!r})"
        )
