from __future__ import annotations

import importlib
import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path

from plasmid_oracle.errors import ProviderUnavailableError
from plasmid_oracle.execution import ProcessRunner, SubprocessRunner
from plasmid_oracle.providers._external import (
    ExecutableResolver,
    default_executable_resolver,
    require_executable,
)


@dataclass(frozen=True, slots=True)
class DatabaseSetupResult:
    component: str
    path: Path | None
    detail: str


def _setup_plannotate(*, force: bool) -> DatabaseSetupResult:
    if importlib.util.find_spec("plannotate") is None:
        raise ProviderUnavailableError(
            "pLannotate is not installed; install plasmid-oracle[plannotate]"
        )
    resources = importlib.import_module("plannotate.resources")
    auto_download = os.environ.get("PLANNOTATE_AUTO_DOWNLOAD")
    os.environ["PLANNOTATE_AUTO_DOWNLOAD"] = "1"
    try:
        installed = Path(resources.download_db(force=force))
    finally:
        if auto_download is None:
            os.environ.pop("PLANNOTATE_AUTO_DOWNLOAD", None)
        else:
            os.environ["PLANNOTATE_AUTO_DOWNLOAD"] = auto_download
    return DatabaseSetupResult(
        component="plannotate",
        path=installed,
        detail="pLannotate database installed and checksum-verified by pLannotate",
    )


def setup(
    component: str,
    *,
    force: bool = False,
    mob_database_dir: Path | None = None,
    runner: ProcessRunner | None = None,
    executable_resolver: ExecutableResolver = default_executable_resolver,
    timeout_seconds: float = 7200,
) -> DatabaseSetupResult:
    normalized = component.strip().lower().replace("-", "_")
    process_runner = runner or SubprocessRunner(default_timeout_seconds=timeout_seconds)

    if normalized == "plannotate":
        return _setup_plannotate(force=force)

    if normalized in {"amrfinder", "amrfinderplus"}:
        executable = require_executable("amrfinder", executable_resolver)
        command = [executable, "--force_update" if force else "--update"]
        process_runner.run(command, timeout_seconds=timeout_seconds)
        return DatabaseSetupResult(
            component="amrfinderplus",
            path=None,
            detail="AMRFinderPlus database updated in its upstream default directory",
        )

    if normalized in {"mob", "mob_suite"}:
        database_dir = mob_database_dir
        if database_dir is None:
            configured = os.environ.get("PLASMID_ORACLE_MOB_DATABASE")
            database_dir = Path(configured) if configured else None
        if database_dir is None:
            raise ValueError(
                "MOB-suite setup requires mob_database_dir or PLASMID_ORACLE_MOB_DATABASE"
            )
        database_dir = database_dir.expanduser()
        executable = require_executable("mob_init", executable_resolver)
        process_runner.run(
            (
                executable,
                "--database_directory",
                os.fspath(database_dir),
            ),
            timeout_seconds=timeout_seconds,
        )
        return DatabaseSetupResult(
            component="mob_suite",
            path=database_dir,
            detail="MOB-suite database initialized",
        )

    raise ValueError("Unknown database component; expected plannotate, amrfinderplus, or mob_suite")
