from __future__ import annotations

import os
from pathlib import Path
from typing import cast

from plasmid_oracle.pipeline import AnnotationProvider
from plasmid_oracle.providers.amrfinder import AMRFinderPlusProvider
from plasmid_oracle.providers.mob_typer import MobTyperProvider
from plasmid_oracle.providers.plannotate import PlannotateProvider
from plasmid_oracle.providers.pyrodigal import PyrodigalProvider


def _optional_path(environment_name: str) -> Path | None:
    value = os.environ.get(environment_name)
    return Path(value) if value else None


def providers_for_mode(mode: str) -> tuple[AnnotationProvider, ...]:
    pyrodigal = PyrodigalProvider()
    if mode in {"minimal", "fast"}:
        return (pyrodigal,)
    if mode not in {"standard", "deep"}:
        raise ValueError(f"Unsupported annotation mode: {mode!r}")

    return (
        cast(AnnotationProvider, pyrodigal),
        cast(AnnotationProvider, PlannotateProvider()),
        cast(
            AnnotationProvider,
            AMRFinderPlusProvider(
                executable=os.environ.get(
                    "PLASMID_ORACLE_AMRFINDER_EXECUTABLE",
                    "amrfinder",
                ),
                database_dir=_optional_path("PLASMID_ORACLE_AMRFINDER_DATABASE"),
            ),
        ),
        cast(
            AnnotationProvider,
            MobTyperProvider(
                executable=os.environ.get(
                    "PLASMID_ORACLE_MOB_TYPER_EXECUTABLE",
                    "mob_typer",
                ),
                database_dir=_optional_path("PLASMID_ORACLE_MOB_DATABASE"),
            ),
        ),
    )
