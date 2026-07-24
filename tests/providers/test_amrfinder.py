from __future__ import annotations

from pathlib import Path

import plasmid_oracle as po
from plasmid_oracle.execution import ProcessResult
from plasmid_oracle.providers.amrfinder import (
    AMRFinderPlusProvider,
    parse_amrfinder_tsv,
)


class AMRFinderRunner:
    def __init__(self, report: str) -> None:
        self.report = report
        self.calls: list[tuple[str, ...]] = []
        self.input_fasta = ""

    def run(self, argv, **kwargs) -> ProcessResult:
        del kwargs
        command = tuple(str(argument) for argument in argv)
        self.calls.append(command)
        if "--database_version" in command:
            return ProcessResult(
                argv=command,
                returncode=0,
                stdout=(
                    "Software directory: /opt/amrfinder/\n"
                    "Software version: 4.0.23\n"
                    "Database directory: /opt/amrfinder/data/latest\n"
                    "Database version: 2026-06-30.1\n"
                ),
                stderr="",
                runtime_seconds=0.01,
            )

        input_path = Path(command[command.index("--nucleotide") + 1])
        output_path = Path(command[command.index("--output") + 1])
        self.input_fasta = input_path.read_text(encoding="ascii")
        output_path.write_text(self.report, encoding="utf-8")
        return ProcessResult(
            argv=command,
            returncode=0,
            stdout="",
            stderr="",
            runtime_seconds=0.02,
        )


def test_amrfinder_tsv_is_normalized_to_amr_annotations() -> None:
    sequence = po.SequenceInfo.from_raw("A" * 1500, topology="linear")
    report = Path("tests/fixtures/amrfinder.tsv").read_text(encoding="utf-8")

    result = parse_amrfinder_tsv(
        report,
        sequence=sequence,
        provider_version="1.0",
        tool_version="4.0.23",
        database_version="2026-06-30.1",
    )

    complete, partial = result.annotations
    assert complete.name == "blaTEM-156"
    assert complete.feature_type == "antimicrobial_resistance_gene"
    assert complete.location == po.Location.from_bounds(
        100,
        958,
        sequence_length=1500,
        topology="linear",
        strand="+",
    )
    assert complete.metrics.identity == 1.0
    assert complete.metrics.coverage == 1.0
    assert complete.integrity is po.Integrity.COMPLETE
    assert complete.canonical_ids == ("WP_061158039.1", "blaTEM-156")

    assert partial.location.strand is po.Strand.REVERSE
    assert partial.integrity is po.Integrity.PARTIAL
    assert partial.metrics.coverage == 0.2528


def test_amrfinder_parser_maps_hits_from_a_doubled_circular_query() -> None:
    sequence = po.SequenceInfo.from_raw("A" * 1000, topology="circular")
    report = (
        "Contig id\tStart\tStop\tStrand\tElement symbol\tElement name\t"
        "Type\tSubtype\tMethod\t% Coverage of reference\t% Identity to reference\n"
        "plasmid\t951\t1050\t+\tblaWRAP\twrapped AMR\tAMR\tAMR\tEXACTX\t100\t100\n"
        "plasmid\t1051\t1150\t+\tblaCOPY\tsecond-copy hit\tAMR\tAMR\tEXACTX\t100\t100\n"
    )

    result = parse_amrfinder_tsv(
        report,
        sequence=sequence,
        provider_version="1.0",
        tool_version="4.0.23",
        database_version="2026-06-30.1",
        circular_query_was_doubled=True,
    )

    assert len(result.annotations) == 1
    assert result.annotations[0].location.spans == (
        po.Span(950, 1000),
        po.Span(0, 50),
    )


def test_amrfinder_provider_runs_a_versioned_nucleotide_search() -> None:
    report = Path("tests/fixtures/amrfinder.tsv").read_text(encoding="utf-8")
    runner = AMRFinderRunner(report)
    provider = AMRFinderPlusProvider(
        runner=runner,
        executable="amrfinder",
        executable_resolver=lambda executable: f"/tools/{executable}",
        plus=True,
    )
    sequence = po.SequenceInfo.from_raw("A" * 1500, topology="linear")

    result = provider.run(
        sequence,
        po.ProviderContext(mode="standard", threads=3, timeout_seconds=30),
    )

    assert len(result.annotations) == 2
    search_call = runner.calls[-1]
    assert search_call[0] == "/tools/amrfinder"
    assert "--plus" in search_call
    assert search_call[search_call.index("--threads") + 1] == "3"
    assert runner.input_fasta.startswith(">plasmid_oracle\n")


def test_amrfinder_provider_doubles_a_circular_query() -> None:
    runner = AMRFinderRunner(
        "Contig id\tStart\tStop\tStrand\tElement symbol\tType\tSubtype\tMethod\n"
    )
    provider = AMRFinderPlusProvider(
        runner=runner,
        executable_resolver=lambda executable: executable,
    )
    sequence = po.SequenceInfo.from_raw("ATGC" * 250, topology="circular")

    provider.run(
        sequence,
        po.ProviderContext(mode="standard"),
    )

    fasta_sequence = "".join(runner.input_fasta.splitlines()[1:])
    assert fasta_sequence == sequence.bases * 2
