from __future__ import annotations

import importlib
import importlib.util
import shutil
import warnings
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import ClassVar

from plasmid_oracle.errors import ProviderUnavailableError
from plasmid_oracle.model import (
    AbsenceSemantics,
    Annotation,
    AnnotationSource,
    BiologicalConcept,
    BiologicalConceptType,
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
from plasmid_oracle.providers._parsing import (
    clean_qualifiers,
    clean_text,
    fraction_from_percent,
    optional_float,
    required_int,
)

_FEATURE_TYPES = {
    "origin of replication": "rep_origin",
    "rep_origin": "rep_origin",
    "cds": "CDS",
}


def _plannotate_version() -> str:
    try:
        return distribution_version("plannotate-python")
    except PackageNotFoundError:
        return "unknown"


def _feature_type(value: object) -> str:
    rendered = clean_text(value) or "misc_feature"
    return _FEATURE_TYPES.get(rendered.lower(), rendered)


def _strand(value: object) -> Strand:
    try:
        frame = int(float(str(value)))
    except (TypeError, ValueError):
        return Strand.UNKNOWN
    if frame > 0:
        return Strand.FORWARD
    if frame < 0:
        return Strand.REVERSE
    return Strand.UNKNOWN


def _is_true(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes"}


def _concept_type(feature_type: str, name: str) -> BiologicalConceptType:
    normalized_type = feature_type.casefold()
    normalized_name = name.casefold()
    if normalized_type in {"rep_origin", "origin_of_replication"}:
        return BiologicalConceptType.ORIGIN
    if normalized_type == "promoter":
        return BiologicalConceptType.PROMOTER
    if normalized_type == "terminator":
        return BiologicalConceptType.TERMINATOR
    if "epitope" in normalized_name:
        return BiologicalConceptType.EPITOPE_TAG
    if "tag" in normalized_type or "tag" in normalized_name:
        return BiologicalConceptType.PROTEIN_TAG
    return BiologicalConceptType.GENE


def parse_plannotate_records(
    records: Iterable[Mapping[str, object]],
    *,
    sequence: SequenceInfo,
    provider_version: str,
    tool_version: str,
    database_versions: Mapping[str, str],
) -> ProviderResult:
    annotations: list[Annotation] = []
    for index, row in enumerate(records, start=1):
        start = required_int(row, "qstart")
        end = required_int(row, "qend")
        database = clean_text(row.get("db"))
        accession = clean_text(row.get("sseqid"))
        name = clean_text(row.get("Feature")) or accession or f"pLannotate feature {index}"
        feature_type = _feature_type(row.get("Type"))
        source = AnnotationSource(
            provider="plannotate",
            provider_version=provider_version,
            tool_version=tool_version,
            database=database,
            database_version=database_versions.get(database or ""),
        )
        metrics = EvidenceMetrics(
            identity=fraction_from_percent(row, "pident"),
            coverage=fraction_from_percent(row, "abs percmatch", "percmatch"),
            score=optional_float(row, "score"),
            evalue=optional_float(row, "evalue"),
        )
        annotations.append(
            Annotation(
                annotation_id=f"plannotate:{index}",
                feature_type=feature_type,
                name=name,
                location=Location.from_bounds(
                    start,
                    end,
                    sequence_length=sequence.length,
                    topology=sequence.topology,
                    strand=_strand(row.get("sframe")),
                ),
                source=source,
                canonical_ids=(accession,) if accession else (),
                integrity=(
                    Integrity.PARTIAL if _is_true(row.get("fragment")) else Integrity.COMPLETE
                ),
                metrics=metrics,
                nucleotide_sequence=clean_text(row.get("qseq")),
                qualifiers=clean_qualifiers(row),
                concepts=(
                    BiologicalConcept(
                        concept_type=_concept_type(feature_type, name),
                        name=name,
                        canonical_id=accession,
                        aliases=(database,) if database is not None else (),
                    ),
                ),
            )
        )

    return ProviderResult(
        annotations=tuple(annotations),
        tool_version=tool_version,
        database_versions=database_versions,
    )


@dataclass(frozen=True, slots=True)
class PlannotateProvider:
    required_executables: tuple[str, ...] = ("blastn", "diamond", "cmscan", "rg")

    spec: ClassVar[ProviderSpec] = ProviderSpec(
        name="plannotate",
        version="1",
        modes=("standard", "deep"),
        capabilities=(
            ProviderCapability(
                concept="engineered_part",
                absence_semantics=AbsenceSemantics.BOUNDED_CATALOG,
                scope={"database": "pLannotate"},
            ),
            ProviderCapability(
                concept="replication_component",
                absence_semantics=AbsenceSemantics.BOUNDED_CATALOG,
                scope={"database": "pLannotate"},
            ),
            ProviderCapability(
                concept="selectable_marker",
                absence_semantics=AbsenceSemantics.BOUNDED_CATALOG,
                scope={"database": "pLannotate"},
            ),
            ProviderCapability(
                concept="promoter",
                absence_semantics=AbsenceSemantics.BOUNDED_CATALOG,
                scope={"database": "pLannotate"},
            ),
            ProviderCapability(
                concept="origin",
                absence_semantics=AbsenceSemantics.BOUNDED_CATALOG,
                scope={"database": "pLannotate"},
            ),
            ProviderCapability(
                concept="terminator",
                absence_semantics=AbsenceSemantics.BOUNDED_CATALOG,
                scope={"database": "pLannotate"},
            ),
            ProviderCapability(
                concept="protein_tag",
                absence_semantics=AbsenceSemantics.BOUNDED_CATALOG,
                scope={"database": "pLannotate"},
            ),
            ProviderCapability(
                concept="epitope_tag",
                absence_semantics=AbsenceSemantics.BOUNDED_CATALOG,
                scope={"database": "pLannotate"},
            ),
        ),
    )

    def run(
        self,
        sequence: SequenceInfo,
        context: ProviderContext,
    ) -> ProviderResult:
        del context
        if importlib.util.find_spec("plannotate") is None:
            raise ProviderUnavailableError(
                "pLannotate is not installed; install plasmid-oracle[plannotate]"
            )
        missing = tuple(
            executable
            for executable in self.required_executables
            if shutil.which(executable) is None
        )
        if missing:
            rendered = ", ".join(missing)
            raise ProviderUnavailableError(
                f"pLannotate external executable(s) not found: {rendered}"
            )

        annotate_module = importlib.import_module("plannotate.annotate")
        resources = importlib.import_module("plannotate.resources")
        database_dir = Path(resources.get_db_dir(download=False))
        if not database_dir.is_dir():
            raise ProviderUnavailableError(
                "pLannotate databases are not installed; run the explicit setup command"
            )

        yaml_path = resources.get_yaml_path()
        database_config = resources.get_yaml(yaml_path, db_dir=database_dir)
        database_versions = {
            str(name): str(config.get("version", "unknown"))
            for name, config in database_config.items()
        }
        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            frame = annotate_module.annotate(
                sequence.bases,
                yaml_file=yaml_path,
                linear=sequence.topology == Topology.LINEAR,
                is_detailed=True,
            )
        if not hasattr(frame, "to_dict"):
            raise TypeError("pLannotate did not return a DataFrame-compatible result")
        records = frame.to_dict(orient="records")
        tool_version = _plannotate_version()
        result = parse_plannotate_records(
            records,
            sequence=sequence,
            provider_version=self.spec.version,
            tool_version=tool_version,
            database_versions=database_versions,
        )
        warning_messages = tuple(
            sorted(
                {
                    f"{warning.category.__name__}: {warning.message}"
                    for warning in caught_warnings
                    if not issubclass(warning.category, (FutureWarning, ResourceWarning))
                }
            )
        )
        return replace(result, warnings=warning_messages)

    def diagnose(self, context: ProviderContext) -> ProviderDiagnostic:
        del context
        issues: list[str] = []
        tool_version: str | None = None
        database_versions: dict[str, str] = {}
        if importlib.util.find_spec("plannotate") is None:
            issues.append("pLannotate is not installed; install plasmid-oracle[plannotate]")
        else:
            try:
                resources = importlib.import_module("plannotate.resources")
                tool_version = _plannotate_version()
                database_dir = Path(resources.get_db_dir(download=False))
                if not database_dir.is_dir():
                    issues.append("pLannotate databases are not installed")
                else:
                    yaml_path = resources.get_yaml_path()
                    database_config = resources.get_yaml(yaml_path, db_dir=database_dir)
                    database_versions = {
                        str(name): str(config.get("version", "unknown"))
                        for name, config in database_config.items()
                    }
            except Exception as error:
                issues.append(str(error))

        missing = tuple(
            executable
            for executable in self.required_executables
            if shutil.which(executable) is None
        )
        if missing:
            issues.append(f"External executable(s) not found: {', '.join(missing)}")
        return ProviderDiagnostic(
            name=self.spec.name,
            available=not issues,
            provider_version=self.spec.version,
            tool_version=tool_version,
            database_versions=database_versions,
            issues=tuple(issues),
            capabilities=self.spec.capabilities,
        )
