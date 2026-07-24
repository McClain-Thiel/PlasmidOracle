from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

from plasmid_oracle import __version__
from plasmid_oracle.api import annotate
from plasmid_oracle.databases import setup as setup_database
from plasmid_oracle.errors import PlasmidOracleError
from plasmid_oracle.pipeline import DoctorReport, doctor
from plasmid_oracle.reporting import render_text
from plasmid_oracle.serialization import to_json


def _single_fasta(path: Path) -> tuple[str, str]:
    identifier: str | None = None
    sequence_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(">"):
            if identifier is not None:
                raise ValueError("FASTA input must contain exactly one sequence")
            identifier = line[1:].split(maxsplit=1)[0] or path.stem
        elif line.strip():
            if identifier is None:
                raise ValueError("FASTA sequence data appeared before its header")
            sequence_lines.append(line.strip())
    if identifier is None or not sequence_lines:
        raise ValueError("FASTA input does not contain a sequence")
    return identifier, "".join(sequence_lines)


def _doctor_payload(report: DoctorReport) -> dict[str, object]:
    return {
        "mode": report.mode,
        "ready": report.ready,
        "providers": [
            {
                "name": provider.name,
                "available": provider.available,
                "provider_version": provider.provider_version,
                "tool_version": provider.tool_version,
                "database_versions": dict(provider.database_versions),
                "issues": list(provider.issues),
            }
            for provider in report.providers
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plasmid-oracle",
        description="Evidence-first plasmid annotation and characterization",
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)

    annotate_parser = commands.add_parser("annotate", help="Annotate one plasmid")
    source = annotate_parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sequence", help="Raw DNA sequence")
    source.add_argument("--fasta", type=Path, help="Single-record FASTA file")
    annotate_parser.add_argument(
        "--topology",
        choices=("circular", "linear"),
        default="circular",
    )
    annotate_parser.add_argument(
        "--mode",
        choices=("minimal", "fast", "standard", "deep"),
        default="minimal",
    )
    annotate_parser.add_argument("--threads", type=int, default=1)
    annotate_parser.add_argument(
        "--provider-workers",
        type=int,
        default=1,
        help="Maximum providers to run concurrently within the total thread budget",
    )
    annotate_parser.add_argument("--timeout", type=float, default=600.0)
    annotate_parser.add_argument(
        "--cache",
        action="store_true",
        help="Reuse results with matching sequence, tool, database, and parameter identity",
    )
    annotate_parser.add_argument("--cache-dir", type=Path)
    annotate_parser.add_argument(
        "--tolerant",
        action="store_true",
        help="Return partial results and record unavailable or failed providers",
    )
    annotate_parser.add_argument("--output", type=Path)
    annotate_parser.add_argument(
        "--format",
        choices=("text", "json"),
        help="Output format; defaults to text on stdout and JSON for files",
    )

    doctor_parser = commands.add_parser("doctor", help="Check provider readiness")
    doctor_parser.add_argument(
        "--mode",
        choices=("minimal", "fast", "standard", "deep"),
        default="standard",
    )
    doctor_parser.add_argument("--json", action="store_true")
    doctor_parser.add_argument("--threads", type=int, default=1)

    setup_parser = commands.add_parser(
        "setup",
        help="Install or update an external provider database",
    )
    setup_parser.add_argument(
        "component",
        choices=("plannotate", "amrfinderplus", "mob-suite"),
    )
    setup_parser.add_argument("--force", action="store_true")
    setup_parser.add_argument(
        "--mob-database",
        type=Path,
        help="MOB-suite database directory",
    )
    setup_parser.add_argument("--timeout", type=float, default=7200.0)
    setup_parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        if arguments.command == "doctor":
            report = doctor(mode=arguments.mode, threads=arguments.threads)
            payload = _doctor_payload(report)
            if arguments.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                print(f"Mode: {report.mode} ({'ready' if report.ready else 'not ready'})")
                for provider in report.providers:
                    state = "ready" if provider.available else "unavailable"
                    print(f"{provider.name}: {state}")
                    for issue in provider.issues:
                        print(f"  {issue}")
            return 0 if report.ready else 1

        if arguments.command == "setup":
            result = setup_database(
                arguments.component,
                force=arguments.force,
                mob_database_dir=arguments.mob_database,
                timeout_seconds=arguments.timeout,
            )
            payload = {
                "component": result.component,
                "path": str(result.path) if result.path is not None else None,
                "detail": result.detail,
            }
            if arguments.json:
                print(json.dumps(payload, indent=2, sort_keys=True))
            else:
                print(result.detail)
                if result.path is not None:
                    print(f"Path: {result.path}")
            return 0

        metadata: dict[str, object] = {}
        sequence = arguments.sequence
        if arguments.fasta is not None:
            identifier, sequence = _single_fasta(arguments.fasta)
            metadata["id"] = identifier
            metadata["source"] = str(arguments.fasta)
        assert sequence is not None
        plasmid = annotate(
            seq=sequence,
            topology=arguments.topology,
            mode=arguments.mode,
            source_metadata=metadata,
            strict=not arguments.tolerant,
            threads=arguments.threads,
            timeout_seconds=arguments.timeout,
            cache=arguments.cache,
            cache_dir=arguments.cache_dir,
            provider_workers=arguments.provider_workers,
        )
        output_format = arguments.format or ("json" if arguments.output is not None else "text")
        output = to_json(plasmid) if output_format == "json" else render_text(plasmid)
        if arguments.output is None:
            print(output)
        else:
            arguments.output.parent.mkdir(parents=True, exist_ok=True)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{arguments.output.name}.",
                dir=arguments.output.parent,
                text=True,
            )
            try:
                with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                    temporary.write(output + "\n")
                    temporary.flush()
                    os.fsync(temporary.fileno())
                os.replace(temporary_name, arguments.output)
            except BaseException:
                Path(temporary_name).unlink(missing_ok=True)
                raise
        return 0
    except (PlasmidOracleError, ValueError, OSError) as error:
        print(f"plasmid-oracle: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
