from __future__ import annotations

import csv
import io
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import ClassVar

from plasmid_oracle.errors import ProviderUnavailableError
from plasmid_oracle.execution import ProcessRunner, SubprocessRunner
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
    SequenceVariant,
    Strand,
    Topology,
    VariantCoordinateSystem,
)
from plasmid_oracle.pipeline import (
    ProviderContext,
    ProviderDiagnostic,
    ProviderResult,
    ProviderSpec,
)
from plasmid_oracle.providers._external import (
    ExecutableResolver,
    default_executable_resolver,
    require_executable,
    require_output,
    write_fasta,
)
from plasmid_oracle.providers._parsing import (
    clean_qualifiers,
    first_text,
    fraction_from_percent,
    required_int,
)


def _integrity(method: str | None) -> Integrity:
    normalized = (method or "").upper()
    if "INTERNAL_STOP" in normalized:
        return Integrity.INTERRUPTED
    if "PARTIAL" in normalized:
        return Integrity.PARTIAL
    return Integrity.COMPLETE


def _feature_type(element_type: str | None, subtype: str | None, method: str | None) -> str:
    normalized_type = (element_type or "").upper()
    normalized_subtype = (subtype or "").upper()
    normalized_method = (method or "").upper()
    if normalized_subtype == "POINT" or normalized_method.startswith("POINT"):
        return "sequence_variant"
    if normalized_type == "AMR":
        return "antimicrobial_resistance_gene"
    if normalized_type == "VIRULENCE":
        return "virulence_factor"
    if normalized_type == "STRESS":
        return "stress_response_gene"
    return "amrfinder_hit"


def _concepts(
    *,
    feature_type: str,
    symbol: str | None,
    element_name: str | None,
    accession: str | None,
    hierarchy: str | None,
    typed_row: dict[str, object],
) -> tuple[BiologicalConcept, ...]:
    name = symbol or element_name
    if name is None:
        return ()
    aliases = tuple(
        value for value in (element_name, hierarchy) if value is not None and value != name
    )
    metadata = {
        key: value
        for key, value in {
            "class": first_text(typed_row, "Class"),
            "subclass": first_text(typed_row, "Subclass"),
        }.items()
        if value is not None
    }
    concept_type = (
        BiologicalConceptType.RESISTANCE_MARKER
        if feature_type == "antimicrobial_resistance_gene"
        else BiologicalConceptType.SEQUENCE_VARIANT
        if feature_type == "sequence_variant"
        else BiologicalConceptType.GENE
    )
    return (
        BiologicalConcept(
            concept_type=concept_type,
            name=name,
            canonical_id=accession or hierarchy,
            aliases=aliases,
            metadata=metadata,
        ),
    )


def _variant(typed_row: dict[str, object], *, gene: str | None) -> SequenceVariant | None:
    notation = first_text(
        typed_row,
        "Element symbol",
        "Element name",
        "Mutation",
        "Point mutation",
        "Sequence name",
    )
    if notation is None:
        return None
    match = re.search(
        r"(?:(?P<gene>[A-Za-z0-9_.-]+)[_:\s-]+)?"
        r"(?P<reference>[A-Za-z*])(?P<position>\d+)(?P<alternate>[A-Za-z*])",
        notation,
    )
    position = int(match.group("position")) if match is not None else None
    return SequenceVariant(
        canonical_notation=notation,
        coordinate_system=VariantCoordinateSystem.PROTEIN,
        gene=gene or (match.group("gene") if match is not None else None),
        position=position,
        reference_residue=match.group("reference") if match is not None else None,
        alternate_residue=match.group("alternate") if match is not None else None,
        metadata={
            key: value
            for key, value in {
                "method": first_text(typed_row, "Method"),
                "scope": first_text(typed_row, "Scope"),
            }.items()
            if value is not None
        },
    )


def _location_from_amrfinder(
    row: dict[str, object],
    *,
    sequence: SequenceInfo,
    circular_query_was_doubled: bool,
) -> Location | None:
    first = required_int(row, "Start")
    second = required_int(row, "Stop")
    start = min(first, second) - 1
    raw_end = max(first, second)

    if circular_query_was_doubled:
        if sequence.topology is not Topology.CIRCULAR:
            raise ValueError("A doubled AMRFinder query requires circular topology")
        if start >= sequence.length:
            return None
        if raw_end - start > sequence.length:
            raise ValueError("AMRFinder hit is longer than the source plasmid")
        end = raw_end - sequence.length if raw_end > sequence.length else raw_end
    else:
        end = raw_end

    strand_value = str(row.get("Strand", "")).strip()
    strand = {
        "+": Strand.FORWARD,
        "-": Strand.REVERSE,
    }.get(strand_value or "", Strand.UNKNOWN)
    return Location.from_bounds(
        start,
        end,
        sequence_length=sequence.length,
        topology=sequence.topology,
        strand=strand,
    )


def parse_amrfinder_tsv(
    report: str,
    *,
    sequence: SequenceInfo,
    provider_version: str,
    tool_version: str,
    database_version: str,
    circular_query_was_doubled: bool = False,
) -> ProviderResult:
    rows = list(csv.DictReader(io.StringIO(report), delimiter="\t")) if report.strip() else []
    annotations: list[Annotation] = []
    for row in rows:
        typed_row: dict[str, object] = dict(row)
        location = _location_from_amrfinder(
            typed_row,
            sequence=sequence,
            circular_query_was_doubled=circular_query_was_doubled,
        )
        if location is None:
            continue

        symbol = first_text(typed_row, "Element symbol", "Gene symbol")
        element_name = first_text(typed_row, "Element name", "Sequence name")
        method = first_text(typed_row, "Method")
        element_type = first_text(typed_row, "Type", "Element type")
        subtype = first_text(typed_row, "Subtype", "Element subtype")
        accession = first_text(
            typed_row,
            "Closest reference accession",
            "Accession of closest sequence",
        )
        hierarchy = first_text(typed_row, "Hierarchy node")
        canonical_ids = tuple(value for value in (accession, hierarchy) if value is not None)
        feature_type = _feature_type(element_type, subtype, method)
        variant = _variant(typed_row, gene=symbol) if feature_type == "sequence_variant" else None
        source = AnnotationSource(
            provider="amrfinderplus",
            provider_version=provider_version,
            tool_version=tool_version,
            database="AMRFinderPlus",
            database_version=database_version,
        )
        annotations.append(
            Annotation(
                annotation_id=f"amrfinderplus:{len(annotations) + 1}",
                feature_type=feature_type,
                name=symbol or element_name or f"AMRFinderPlus hit {len(annotations) + 1}",
                location=location,
                source=source,
                canonical_ids=canonical_ids,
                integrity=_integrity(method),
                metrics=EvidenceMetrics(
                    identity=fraction_from_percent(
                        typed_row,
                        "% Identity to reference",
                        "% Identity to reference sequence",
                    ),
                    coverage=fraction_from_percent(
                        typed_row,
                        "% Coverage of reference",
                        "% Coverage of reference sequence",
                    ),
                ),
                qualifiers=clean_qualifiers(typed_row),
                concepts=_concepts(
                    feature_type=feature_type,
                    symbol=symbol,
                    element_name=element_name,
                    accession=accession,
                    hierarchy=hierarchy,
                    typed_row=typed_row,
                ),
                variants=(variant,) if variant is not None else (),
            )
        )

    versions = {"AMRFinderPlus": database_version} if database_version else {}
    return ProviderResult(
        annotations=tuple(annotations),
        tool_version=tool_version,
        database_versions=versions,
    )


def _parse_version_report(report: str) -> tuple[str, str]:
    values: dict[str, str] = {}
    for line in report.splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key.strip().lower()] = value.strip().strip("'\"")
    software = values.get("software version")
    database = values.get("database version")
    if not software or not database:
        raise ProviderUnavailableError(
            "AMRFinderPlus did not report both software and database versions"
        )
    return software, database


@dataclass(frozen=True, slots=True)
class AMRFinderPlusProvider:
    runner: ProcessRunner = field(default_factory=SubprocessRunner)
    executable: str = "amrfinder"
    database_dir: Path | None = None
    plus: bool = True
    executable_resolver: ExecutableResolver = default_executable_resolver

    spec: ClassVar[ProviderSpec] = ProviderSpec(
        name="amrfinderplus",
        version="1",
        modes=("standard", "deep"),
        capabilities=(
            ProviderCapability(
                concept="antimicrobial_resistance_gene",
                absence_semantics=AbsenceSemantics.BOUNDED_CATALOG,
                scope={"database": "AMRFinderPlus", "organism": None},
            ),
            ProviderCapability(
                concept="sequence_variant",
                absence_semantics=AbsenceSemantics.BOUNDED_CATALOG,
                scope={"database": "AMRFinderPlus", "organism": None},
            ),
            ProviderCapability(
                concept="stress_response_gene",
                absence_semantics=AbsenceSemantics.BOUNDED_CATALOG,
                scope={"database": "AMRFinderPlus", "organism": None},
            ),
            ProviderCapability(
                concept="virulence_factor",
                absence_semantics=AbsenceSemantics.BOUNDED_CATALOG,
                scope={"database": "AMRFinderPlus", "organism": None},
            ),
        ),
    )

    def run(
        self,
        sequence: SequenceInfo,
        context: ProviderContext,
    ) -> ProviderResult:
        executable = require_executable(self.executable, self.executable_resolver)
        version_command = [executable, "--database_version"]
        if self.database_dir is not None:
            version_command.extend(("--database", os.fspath(self.database_dir)))
        version_result = self.runner.run(
            version_command,
            timeout_seconds=min(context.timeout_seconds, 60),
        )
        tool_version, database_version = _parse_version_report(version_result.stdout)

        circular_query = sequence.topology is Topology.CIRCULAR
        query = sequence.bases * 2 if circular_query else sequence.bases
        with TemporaryDirectory(prefix="plasmid-oracle-amrfinder-") as temp_dir:
            workdir = Path(temp_dir)
            input_path = workdir / "plasmid.fasta"
            output_path = workdir / "amrfinder.tsv"
            write_fasta(input_path, query)

            command = [
                executable,
                "--nucleotide",
                os.fspath(input_path),
                "--output",
                os.fspath(output_path),
                "--threads",
                str(context.threads),
                "--print_node",
                "--quiet",
            ]
            if self.plus:
                command.append("--plus")
            if self.database_dir is not None:
                command.extend(("--database", os.fspath(self.database_dir)))

            self.runner.run(
                command,
                cwd=workdir,
                timeout_seconds=context.timeout_seconds,
            )
            report = require_output(output_path, self.spec.name)

        return parse_amrfinder_tsv(
            report,
            sequence=sequence,
            provider_version=self.spec.version,
            tool_version=tool_version,
            database_version=database_version,
            circular_query_was_doubled=circular_query,
        )

    def diagnose(self, context: ProviderContext) -> ProviderDiagnostic:
        resolved = self.executable_resolver(self.executable)
        if resolved is None:
            return ProviderDiagnostic(
                name=self.spec.name,
                available=False,
                provider_version=self.spec.version,
                issues=(f"Executable {self.executable!r} was not found on PATH",),
            )
        try:
            command = [resolved, "--database_version"]
            if self.database_dir is not None:
                command.extend(("--database", os.fspath(self.database_dir)))
            result = self.runner.run(
                command,
                timeout_seconds=min(context.timeout_seconds, 60),
            )
            tool_version, database_version = _parse_version_report(result.stdout)
        except Exception as error:
            return ProviderDiagnostic(
                name=self.spec.name,
                available=False,
                provider_version=self.spec.version,
                issues=(str(error),),
            )
        return ProviderDiagnostic(
            name=self.spec.name,
            available=True,
            provider_version=self.spec.version,
            tool_version=tool_version,
            database_versions={"AMRFinderPlus": database_version},
            capabilities=self.spec.capabilities,
        )
