from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from functools import partial
from pathlib import Path

from plasmid_oracle.evaluation import check, evaluate, requirement_schema, requirements_from_dict
from plasmid_oracle.model import (
    AnalysisManifest,
    Characterization,
    Plasmid,
    SequenceInfo,
    Topology,
)
from plasmid_oracle.pipeline import (
    PIPELINE_VERSION,
    AnnotationProvider,
    run_pipeline,
)
from plasmid_oracle.providers.builtin import providers_for_mode

_VALID_MODES = frozenset({"minimal", "fast", "standard", "deep"})
__all__ = [
    "annotate",
    "annotate_async",
    "check",
    "evaluate",
    "plasmid",
    "requirement_schema",
    "requirements_from_dict",
]


def plasmid(
    *,
    seq: str,
    topology: Topology | str = Topology.CIRCULAR,
    source_metadata: Mapping[str, object] | None = None,
) -> Plasmid:
    return Plasmid(
        sequence=SequenceInfo.from_raw(seq, topology=topology),
        evidence=(),
        annotations=(),
        characterization=Characterization(),
        source_metadata=source_metadata or {},
        analysis=AnalysisManifest(
            pipeline_version=PIPELINE_VERSION,
            mode="none",
        ),
    )


def annotate(
    *,
    seq: str,
    topology: Topology | str = Topology.CIRCULAR,
    mode: str = "minimal",
    providers: Iterable[AnnotationProvider] | None = None,
    source_metadata: Mapping[str, object] | None = None,
    strict: bool = True,
    threads: int = 1,
    timeout_seconds: float = 600.0,
    cache: bool = False,
    cache_dir: Path | None = None,
    provider_workers: int = 1,
) -> Plasmid:
    if mode not in _VALID_MODES:
        choices = ", ".join(sorted(_VALID_MODES))
        raise ValueError(f"Unsupported annotation mode {mode!r}; expected one of: {choices}")

    normalized = plasmid(
        seq=seq,
        topology=topology,
        source_metadata=source_metadata,
    )
    selected_providers = providers_for_mode(mode) if providers is None else tuple(providers)
    return run_pipeline(
        normalized,
        mode=mode,
        providers=selected_providers,
        strict=strict,
        threads=threads,
        timeout_seconds=timeout_seconds,
        cache=cache,
        cache_dir=cache_dir,
        provider_workers=provider_workers,
    )


async def annotate_async(
    *,
    seq: str,
    topology: Topology | str = Topology.CIRCULAR,
    mode: str = "minimal",
    providers: Iterable[AnnotationProvider] | None = None,
    source_metadata: Mapping[str, object] | None = None,
    strict: bool = True,
    threads: int = 1,
    timeout_seconds: float = 600.0,
    cache: bool = False,
    cache_dir: Path | None = None,
    provider_workers: int = 1,
) -> Plasmid:
    operation = partial(
        annotate,
        seq=seq,
        topology=topology,
        mode=mode,
        providers=providers,
        source_metadata=source_metadata,
        strict=strict,
        threads=threads,
        timeout_seconds=timeout_seconds,
        cache=cache,
        cache_dir=cache_dir,
        provider_workers=provider_workers,
    )
    return await asyncio.to_thread(operation)
