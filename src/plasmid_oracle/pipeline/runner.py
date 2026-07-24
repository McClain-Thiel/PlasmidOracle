from __future__ import annotations

from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter

from plasmid_oracle.errors import (
    InvalidProviderResultError,
    ProviderExecutionError,
    ProviderUnavailableError,
)
from plasmid_oracle.model import (
    AnalysisManifest,
    Annotation,
    Characterization,
    Plasmid,
    ProviderRun,
    ProviderStatus,
)
from plasmid_oracle.pipeline.cache import ProviderCache, default_cache_dir
from plasmid_oracle.pipeline.diagnostics import ProviderDiagnostic
from plasmid_oracle.pipeline.provider import (
    AnnotationProvider,
    ProviderContext,
    ProviderResult,
)
from plasmid_oracle.resolution import resolve_annotations

PIPELINE_VERSION = "0.2.0a2"


@dataclass(frozen=True, slots=True)
class _ProviderOutcome:
    run: ProviderRun
    result: ProviderResult | None
    warnings: tuple[str, ...] = ()
    error: Exception | None = None


def _validate_result(
    result: ProviderResult,
    *,
    sequence_length: int,
    provider_name: str,
) -> None:
    annotation_ids: set[str] = set()
    evidence_ids: set[str] = set()
    for annotation in result.annotations:
        if not isinstance(annotation, Annotation):
            raise InvalidProviderResultError(
                f"Provider {provider_name!r} returned a non-Annotation result"
            )
        if annotation.location.sequence_length != sequence_length:
            raise InvalidProviderResultError(
                f"Provider {provider_name!r} returned coordinates for a different sequence length"
            )
        if annotation.annotation_id in annotation_ids:
            raise InvalidProviderResultError(
                f"Provider {provider_name!r} returned duplicate annotation ID "
                f"{annotation.annotation_id!r}"
            )
        annotation_ids.add(annotation.annotation_id)
        if annotation.evidence_id in evidence_ids:
            raise InvalidProviderResultError(
                f"Provider {provider_name!r} returned duplicate evidence ID "
                f"{annotation.evidence_id!r}"
            )
        evidence_ids.add(annotation.evidence_id)

    if not isinstance(result.characterization, Characterization):
        raise InvalidProviderResultError(
            f"Provider {provider_name!r} returned a non-Characterization result"
        )
    for calls in (
        result.characterization.replicons,
        result.characterization.relaxases,
        result.characterization.mpf_types,
        result.characterization.orit_sites,
        result.characterization.mobility,
        result.characterization.host_range,
        result.characterization.similarity_hits,
        result.characterization.quality_flags,
    ):
        for call in calls:
            if call.evidence_id in evidence_ids:
                raise InvalidProviderResultError(
                    f"Provider {provider_name!r} returned duplicate evidence ID "
                    f"{call.evidence_id!r}"
                )
            evidence_ids.add(call.evidence_id)


def _run_provider(
    provider: AnnotationProvider,
    *,
    plasmid: Plasmid,
    context: ProviderContext,
    provider_cache: ProviderCache | None,
) -> _ProviderOutcome:
    spec = provider.spec
    started = perf_counter()
    warnings: list[str] = []
    cache_key: tuple[str, dict[str, object]] | None = None

    if provider_cache is not None:
        diagnose = getattr(provider, "diagnose", None)
        if not callable(diagnose):
            warnings.append(f"Cache disabled for {spec.name}: provider has no diagnostic identity")
        else:
            try:
                diagnostic = diagnose(context)
                if not isinstance(diagnostic, ProviderDiagnostic):
                    raise TypeError("diagnose() did not return ProviderDiagnostic")
                if not diagnostic.available:
                    detail = "; ".join(diagnostic.issues) or "provider is unavailable"
                    raise ValueError(detail)
                cache_key = provider_cache.key(
                    spec=spec,
                    sequence=plasmid.sequence,
                    context=context,
                    diagnostic=diagnostic,
                )
                digest, identity = cache_key
                lookup = provider_cache.load(
                    provider_name=spec.name,
                    digest=digest,
                    identity=identity,
                )
                if lookup.warning is not None:
                    warnings.append(lookup.warning)
                if lookup.result is not None:
                    _validate_result(
                        lookup.result,
                        sequence_length=plasmid.sequence.length,
                        provider_name=spec.name,
                    )
                    return _ProviderOutcome(
                        run=ProviderRun(
                            name=spec.name,
                            status=ProviderStatus.CACHED,
                            provider_version=spec.version,
                            tool_version=lookup.result.tool_version,
                            database_versions=lookup.result.database_versions,
                            database_manifests=lookup.result.database_manifests,
                            capabilities=spec.capabilities,
                            parameters=context.parameters,
                            diagnostic_identity=identity,
                            cache_key=digest,
                            runtime_seconds=perf_counter() - started,
                            warnings=lookup.result.warnings,
                        ),
                        result=lookup.result,
                        warnings=tuple(warnings),
                    )
            except Exception as error:
                cache_key = None
                warnings.append(f"Cache disabled for {spec.name}: {error}")

    try:
        result = provider.run(plasmid.sequence, context)
        if not isinstance(result, ProviderResult):
            raise InvalidProviderResultError(
                f"Provider {spec.name!r} did not return ProviderResult"
            )
        _validate_result(
            result,
            sequence_length=plasmid.sequence.length,
            provider_name=spec.name,
        )
    except Exception as error:
        status = (
            ProviderStatus.UNAVAILABLE
            if isinstance(error, ProviderUnavailableError)
            else ProviderStatus.FAILED
        )
        return _ProviderOutcome(
            run=ProviderRun(
                name=spec.name,
                status=status,
                provider_version=spec.version,
                capabilities=spec.capabilities,
                parameters=context.parameters,
                runtime_seconds=perf_counter() - started,
                error=str(error),
            ),
            result=None,
            warnings=tuple(warnings),
            error=error,
        )

    if provider_cache is not None and cache_key is not None:
        digest, identity = cache_key
        try:
            provider_cache.store(
                provider_name=spec.name,
                digest=digest,
                identity=identity,
                result=result,
            )
        except (OSError, TypeError, ValueError) as error:
            warnings.append(f"Could not cache {spec.name}: {error}")

    return _ProviderOutcome(
        run=ProviderRun(
            name=spec.name,
            status=ProviderStatus.COMPLETED,
            provider_version=spec.version,
            tool_version=result.tool_version,
            database_versions=result.database_versions,
            database_manifests=result.database_manifests,
            capabilities=spec.capabilities,
            parameters=context.parameters,
            diagnostic_identity=identity if cache_key is not None else {},
            cache_key=digest if cache_key is not None else None,
            runtime_seconds=perf_counter() - started,
            warnings=result.warnings,
        ),
        result=result,
        warnings=tuple(warnings),
    )


def run_pipeline(
    plasmid: Plasmid,
    *,
    mode: str,
    providers: Iterable[AnnotationProvider],
    strict: bool,
    threads: int = 1,
    timeout_seconds: float = 600.0,
    cache: bool = False,
    cache_dir: Path | None = None,
    provider_workers: int = 1,
) -> Plasmid:
    if threads < 1:
        raise ValueError("threads must be at least 1")
    if provider_workers < 1:
        raise ValueError("provider_workers must be at least 1")
    if provider_workers > threads:
        raise ValueError("provider_workers cannot exceed the total thread budget")

    selected = tuple(providers)
    eligible = tuple(provider for provider in selected if mode in provider.spec.modes)
    worker_count = min(provider_workers, max(1, len(eligible)))
    provider_threads = max(1, threads // worker_count)
    context = ProviderContext(
        mode=mode,
        threads=provider_threads,
        timeout_seconds=timeout_seconds,
        parameters={
            "threads": provider_threads,
            "total_threads": threads,
            "provider_workers": worker_count,
            "timeout_seconds": timeout_seconds,
        },
    )
    provider_cache = ProviderCache(cache_dir or default_cache_dir()) if cache else None
    outcomes: dict[int, _ProviderOutcome] = {}

    runnable = [
        (index, provider) for index, provider in enumerate(selected) if mode in provider.spec.modes
    ]
    if worker_count == 1:
        for index, provider in runnable:
            outcomes[index] = _run_provider(
                provider,
                plasmid=plasmid,
                context=context,
                provider_cache=provider_cache,
            )
            if strict and outcomes[index].error is not None:
                break
    else:
        with ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="plasmid-oracle",
        ) as executor:
            futures = {
                index: executor.submit(
                    _run_provider,
                    provider,
                    plasmid=plasmid,
                    context=context,
                    provider_cache=provider_cache,
                )
                for index, provider in runnable
            }
            outcomes = {index: future.result() for index, future in futures.items()}

    evidence = list(plasmid.evidence)
    characterization = plasmid.characterization
    provider_runs: list[ProviderRun] = []
    manifest_warnings: list[str] = []
    first_error: tuple[str, Exception] | None = None

    for index, provider in enumerate(selected):
        spec = provider.spec
        if mode not in spec.modes:
            provider_runs.append(
                ProviderRun(
                    name=spec.name,
                    status=ProviderStatus.SKIPPED,
                    provider_version=spec.version,
                    capabilities=spec.capabilities,
                    parameters=context.parameters,
                    error=f"Provider does not support mode {mode!r}",
                )
            )
            continue
        outcome = outcomes.get(index)
        if outcome is None:
            break
        provider_runs.append(outcome.run)
        manifest_warnings.extend(outcome.warnings)
        if outcome.error is not None:
            if first_error is None:
                first_error = (spec.name, outcome.error)
            continue
        assert outcome.result is not None
        evidence.extend(outcome.result.annotations)
        characterization = characterization.merged_with(outcome.result.characterization)

    if strict and first_error is not None:
        provider_name, error = first_error
        raise ProviderExecutionError(provider_name, provider_runs) from error

    manifest = AnalysisManifest(
        pipeline_version=PIPELINE_VERSION,
        mode=mode,
        provider_runs=tuple(provider_runs),
        warnings=tuple(manifest_warnings),
    )
    return replace(
        plasmid,
        evidence=tuple(evidence),
        annotations=resolve_annotations(evidence),
        characterization=characterization,
        analysis=manifest,
    )
