from __future__ import annotations

import csv
import io
import os
import re
from dataclasses import dataclass, field
from itertools import zip_longest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import ClassVar

from plasmid_oracle.errors import InvalidProviderResultError, ProviderUnavailableError
from plasmid_oracle.execution import ProcessRunner, SubprocessRunner
from plasmid_oracle.model import (
    AnnotationSource,
    Characterization,
    CharacterizationCall,
    SequenceInfo,
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
    clean_text,
    optional_float,
    split_values,
)


def _typed_calls(
    row: dict[str, object],
    *,
    names_field: str,
    accessions_field: str,
    source: AnnotationSource,
) -> tuple[CharacterizationCall, ...]:
    names = split_values(row.get(names_field))
    accessions = split_values(row.get(accessions_field))
    calls: list[CharacterizationCall] = []
    for name, accession in zip_longest(names, accessions):
        if name is None:
            continue
        qualifiers = {"accession": accession} if accession is not None else {}
        calls.append(
            CharacterizationCall(
                name=name,
                source=source,
                qualifiers=qualifiers,
            )
        )
    return tuple(calls)


def _host_range_calls(
    row: dict[str, object],
    source: AnnotationSource,
) -> tuple[CharacterizationCall, ...]:
    calls: list[CharacterizationCall] = []
    fields = (
        (
            "predicted_host_range_overall_name",
            "predicted_host_range_overall_rank",
            "predicted",
        ),
        ("observed_host_range_ncbi_name", "observed_host_range_ncbi_rank", "observed"),
        ("reported_host_range_lit_name", "reported_host_range_lit_rank", "reported"),
    )
    for name_field, rank_field, basis in fields:
        name = clean_text(row.get(name_field))
        if name is None:
            continue
        qualifiers: dict[str, object] = {"basis": basis}
        rank = clean_text(row.get(rank_field))
        if rank is not None:
            qualifiers["rank"] = rank
        calls.append(CharacterizationCall(name=name, source=source, qualifiers=qualifiers))
    return tuple(calls)


def parse_mob_typer_tsv(
    report: str,
    *,
    provider_version: str,
    tool_version: str,
    database_version: str | None,
) -> ProviderResult:
    rows = list(csv.DictReader(io.StringIO(report), delimiter="\t")) if report.strip() else []
    if not rows:
        return ProviderResult(tool_version=tool_version)
    if len(rows) != 1:
        raise InvalidProviderResultError(
            f"MOB-typer returned {len(rows)} rows for a single plasmid"
        )

    row: dict[str, object] = dict(rows[0])
    source = AnnotationSource(
        provider="mob_typer",
        provider_version=provider_version,
        tool_version=tool_version,
        database="MOB-suite",
        database_version=database_version,
    )
    mobility_name = clean_text(row.get("predicted_mobility"))
    mobility = (
        (CharacterizationCall(name=mobility_name, source=source),)
        if mobility_name is not None
        else ()
    )

    nearest_neighbor = clean_text(row.get("mash_nearest_neighbor"))
    similarity_hits: tuple[CharacterizationCall, ...] = ()
    if nearest_neighbor is not None:
        qualifiers: dict[str, object] = {}
        distance = optional_float(row, "mash_neighbor_distance")
        if distance is not None:
            qualifiers["distance"] = distance
        identification = clean_text(row.get("mash_neighbor_identification"))
        if identification is not None:
            qualifiers["identification"] = identification
        primary_cluster = clean_text(row.get("primary_cluster_id"))
        if primary_cluster is not None:
            qualifiers["primary_cluster_id"] = primary_cluster
        secondary_cluster = clean_text(row.get("secondary_cluster_id"))
        if secondary_cluster is not None:
            qualifiers["secondary_cluster_id"] = secondary_cluster
        similarity_hits = (
            CharacterizationCall(
                name=nearest_neighbor,
                source=source,
                qualifiers=qualifiers,
            ),
        )

    characterization = Characterization(
        replicons=_typed_calls(
            row,
            names_field="rep_type(s)",
            accessions_field="rep_type_accession(s)",
            source=source,
        ),
        relaxases=_typed_calls(
            row,
            names_field="relaxase_type(s)",
            accessions_field="relaxase_type_accession(s)",
            source=source,
        ),
        mpf_types=_typed_calls(
            row,
            names_field="mpf_type",
            accessions_field="mpf_type_accession(s)",
            source=source,
        ),
        orit_sites=_typed_calls(
            row,
            names_field="orit_type(s)",
            accessions_field="orit_accession(s)",
            source=source,
        ),
        mobility=mobility,
        host_range=_host_range_calls(row, source),
        similarity_hits=similarity_hits,
    )
    versions = {"MOB-suite": database_version} if database_version else {}
    return ProviderResult(
        characterization=characterization,
        tool_version=tool_version,
        database_versions=versions,
    )


def _mob_database_version(database_dir: Path) -> str:
    status_path = database_dir / "status.txt"
    if not status_path.is_file():
        raise ProviderUnavailableError(f"MOB-suite database is incomplete: missing {status_path}")
    status = status_path.read_text(encoding="utf-8").strip()
    date_match = re.search(r"\d{4}-\d{2}-\d{2}", status)
    return f"downloaded-{date_match.group(0)}" if date_match else status


@dataclass(frozen=True, slots=True)
class MobTyperProvider:
    database_dir: Path | None
    runner: ProcessRunner = field(default_factory=SubprocessRunner)
    executable: str = "mob_typer"
    executable_resolver: ExecutableResolver = default_executable_resolver

    spec: ClassVar[ProviderSpec] = ProviderSpec(
        name="mob_typer",
        version="1",
        modes=("standard", "deep"),
    )

    def run(
        self,
        sequence: SequenceInfo,
        context: ProviderContext,
    ) -> ProviderResult:
        executable = require_executable(self.executable, self.executable_resolver)
        if self.database_dir is None:
            raise ProviderUnavailableError(
                "MOB-suite database path is not configured; set PLASMID_ORACLE_MOB_DATABASE"
            )
        database_dir = self.database_dir.expanduser().resolve()
        database_version = _mob_database_version(database_dir)
        version_result = self.runner.run(
            (executable, "--version"),
            timeout_seconds=min(context.timeout_seconds, 30),
        )
        version_match = re.search(r"(\d+\.\d+(?:\.\d+)?)", version_result.stdout)
        if version_match is None:
            raise ProviderUnavailableError("MOB-typer did not report a software version")
        tool_version = version_match.group(1)

        with TemporaryDirectory(prefix="plasmid-oracle-mob-typer-") as temp_dir:
            workdir = Path(temp_dir)
            input_path = workdir / "plasmid.fasta"
            output_path = workdir / "mob_typer.tsv"
            write_fasta(input_path, sequence.bases)
            command = (
                executable,
                "--infile",
                os.fspath(input_path),
                "--out_file",
                os.fspath(output_path),
                "--num_threads",
                str(context.threads),
                "--database_directory",
                os.fspath(database_dir),
            )
            process_result = self.runner.run(
                command,
                cwd=workdir,
                timeout_seconds=context.timeout_seconds,
            )
            report = require_output(
                output_path,
                self.spec.name,
                diagnostic=process_result.stderr,
            )

        return parse_mob_typer_tsv(
            report,
            provider_version=self.spec.version,
            tool_version=tool_version,
            database_version=database_version,
        )

    def diagnose(self, context: ProviderContext) -> ProviderDiagnostic:
        resolved = self.executable_resolver(self.executable)
        issues: list[str] = []
        if resolved is None:
            issues.append(f"Executable {self.executable!r} was not found on PATH")
        if self.database_dir is None:
            issues.append(
                "MOB-suite database path is not configured; set PLASMID_ORACLE_MOB_DATABASE"
            )
        if issues:
            return ProviderDiagnostic(
                name=self.spec.name,
                available=False,
                provider_version=self.spec.version,
                issues=tuple(issues),
            )

        assert resolved is not None
        assert self.database_dir is not None
        try:
            database_version = _mob_database_version(self.database_dir.expanduser().resolve())
            version_result = self.runner.run(
                (resolved, "--version"),
                timeout_seconds=min(context.timeout_seconds, 30),
            )
            version_match = re.search(r"(\d+\.\d+(?:\.\d+)?)", version_result.stdout)
            if version_match is None:
                raise ProviderUnavailableError("MOB-typer did not report a software version")
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
            tool_version=version_match.group(1),
            database_versions={"MOB-suite": database_version},
        )
