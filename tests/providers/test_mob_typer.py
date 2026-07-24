from __future__ import annotations

from pathlib import Path

import pytest

import plasmid_oracle as po
from plasmid_oracle.execution import ProcessResult
from plasmid_oracle.providers.mob_typer import (
    MobTyperProvider,
    parse_mob_typer_tsv,
)


class MobTyperRunner:
    def __init__(
        self,
        report: str,
        *,
        create_output: bool = True,
        stderr: str = "",
    ) -> None:
        self.report = report
        self.create_output = create_output
        self.stderr = stderr
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv, **kwargs) -> ProcessResult:
        del kwargs
        command = tuple(str(argument) for argument in argv)
        self.calls.append(command)
        if "--version" in command:
            return ProcessResult(
                argv=command,
                returncode=0,
                stdout="mob_typer 3.1.9\n",
                stderr="",
                runtime_seconds=0.01,
            )

        output_path = Path(command[command.index("--out_file") + 1])
        if self.create_output:
            output_path.write_text(self.report, encoding="utf-8")
        return ProcessResult(
            argv=command,
            returncode=0,
            stdout="",
            stderr=self.stderr,
            runtime_seconds=0.02,
        )


def test_mob_typer_report_is_normalized_to_characterization() -> None:
    report = Path("tests/fixtures/mob_typer.tsv").read_text(encoding="utf-8")

    result = parse_mob_typer_tsv(
        report,
        provider_version="1.0",
        tool_version="3.1.9",
        database_version="downloaded-2026-07-01",
    )

    characterization = result.characterization
    assert [call.name for call in characterization.replicons] == ["IncFIA", "IncFIB"]
    assert characterization.replicons[0].qualifiers["accession"] == "AP001918"
    assert [call.name for call in characterization.relaxases] == ["MOBF"]
    assert [call.name for call in characterization.mpf_types] == ["MPFT"]
    assert [call.name for call in characterization.orit_sites] == ["oriT_F"]
    assert characterization.mobility[0].name == "conjugative"
    assert characterization.host_range[0].name == "Enterobacteriaceae"
    assert characterization.similarity_hits[0].name == "NC_000001"
    assert characterization.similarity_hits[0].qualifiers["distance"] == 0.012


def test_mob_typer_empty_report_is_valid() -> None:
    result = parse_mob_typer_tsv(
        "",
        provider_version="1.0",
        tool_version="3.1.9",
        database_version=None,
    )

    assert result.characterization.replicons == ()


def test_mob_typer_provider_runs_with_an_explicit_database(
    tmp_path: Path,
) -> None:
    report = Path("tests/fixtures/mob_typer.tsv").read_text(encoding="utf-8")
    database = tmp_path / "mob-db"
    database.mkdir()
    (database / "status.txt").write_text(
        "Download date: 2026-07-01. Removing lock file.",
        encoding="utf-8",
    )
    runner = MobTyperRunner(report)
    provider = MobTyperProvider(
        runner=runner,
        database_dir=database,
        executable_resolver=lambda executable: f"/tools/{executable}",
    )

    result = provider.run(
        po.SequenceInfo.from_raw("ATGC" * 1000),
        po.ProviderContext(mode="standard", threads=2),
    )

    assert result.characterization.replicons
    call = runner.calls[-1]
    assert call[0] == "/tools/mob_typer"
    assert call[call.index("--num_threads") + 1] == "2"
    assert call[call.index("--database_directory") + 1] == str(database)


def test_mob_typer_reports_stderr_when_upstream_exits_without_output(
    tmp_path: Path,
) -> None:
    database = tmp_path / "mob-db"
    database.mkdir()
    (database / "status.txt").write_text(
        "Download date: 2026-07-01. Removing lock file.",
        encoding="utf-8",
    )
    provider = MobTyperProvider(
        runner=MobTyperRunner(
            "",
            create_output=False,
            stderr="makeblastdb failed: library version mismatch",
        ),
        database_dir=database,
        executable_resolver=lambda executable: f"/tools/{executable}",
    )

    with pytest.raises(
        po.InvalidProviderResultError,
        match="makeblastdb failed: library version mismatch",
    ):
        provider.run(
            po.SequenceInfo.from_raw("ATGC" * 1000),
            po.ProviderContext(mode="standard"),
        )
