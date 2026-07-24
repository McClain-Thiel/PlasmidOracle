from __future__ import annotations

import os
import shutil
from collections.abc import Callable
from pathlib import Path

from plasmid_oracle.errors import InvalidProviderResultError, ProviderUnavailableError

ExecutableResolver = Callable[[str], str | None]


def default_executable_resolver(executable: str) -> str | None:
    return shutil.which(executable)


def require_executable(
    executable: str,
    resolver: ExecutableResolver,
) -> str:
    resolved = resolver(executable)
    if resolved is None:
        raise ProviderUnavailableError(f"Required executable {executable!r} was not found on PATH")
    return resolved


def write_fasta(path: Path, sequence: str, *, identifier: str = "plasmid_oracle") -> None:
    lines = [f">{identifier}"]
    lines.extend(sequence[index : index + 80] for index in range(0, len(sequence), 80))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def require_output(
    path: Path,
    provider_name: str,
    *,
    diagnostic: str | None = None,
) -> str:
    if not path.is_file():
        detail = f": {diagnostic.strip()}" if diagnostic and diagnostic.strip() else ""
        raise InvalidProviderResultError(
            f"{provider_name} completed without creating expected output "
            f"{os.fspath(path)!r}{detail}"
        )
    return path.read_text(encoding="utf-8")
