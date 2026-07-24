from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from plasmid_oracle._immutability import freeze_mapping
from plasmid_oracle.model import DatabaseIdentity, ProviderCapability
from plasmid_oracle.model.manifest import database_identities_from_versions
from plasmid_oracle.pipeline.provider import AnnotationProvider, ProviderContext


@dataclass(frozen=True, slots=True)
class ProviderDiagnostic:
    name: str
    available: bool
    provider_version: str
    tool_version: str | None = None
    database_versions: Mapping[str, str] = field(default_factory=dict)
    database_manifests: tuple[DatabaseIdentity, ...] = ()
    capabilities: tuple[ProviderCapability, ...] = ()
    issues: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "database_versions", freeze_mapping(self.database_versions))
        database_manifests = (
            tuple(self.database_manifests)
            if self.database_manifests
            else database_identities_from_versions(self.database_versions)
        )
        object.__setattr__(self, "database_manifests", database_manifests)
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(self, "issues", tuple(self.issues))


@dataclass(frozen=True, slots=True)
class DoctorReport:
    mode: str
    providers: tuple[ProviderDiagnostic, ...]

    @property
    def ready(self) -> bool:
        return all(provider.available for provider in self.providers)


def doctor(
    *,
    mode: str = "standard",
    providers: Iterable[AnnotationProvider] | None = None,
    threads: int = 1,
    timeout_seconds: float = 30.0,
) -> DoctorReport:
    if providers is None:
        from plasmid_oracle.providers.builtin import providers_for_mode

        selected = providers_for_mode(mode)
    else:
        selected = tuple(providers)

    context = ProviderContext(
        mode=mode,
        threads=threads,
        timeout_seconds=timeout_seconds,
    )
    diagnostics: list[ProviderDiagnostic] = []
    for provider in selected:
        diagnose = getattr(provider, "diagnose", None)
        if diagnose is None:
            diagnostics.append(
                ProviderDiagnostic(
                    name=provider.spec.name,
                    available=True,
                    provider_version=provider.spec.version,
                    capabilities=provider.spec.capabilities,
                    issues=("Custom provider does not expose a preflight diagnostic",),
                )
            )
            continue
        try:
            diagnostic = diagnose(context)
        except Exception as error:
            diagnostic = ProviderDiagnostic(
                name=provider.spec.name,
                available=False,
                provider_version=provider.spec.version,
                capabilities=provider.spec.capabilities,
                issues=(str(error),),
            )
        if not diagnostic.capabilities and provider.spec.capabilities:
            diagnostic = ProviderDiagnostic(
                name=diagnostic.name,
                available=diagnostic.available,
                provider_version=diagnostic.provider_version,
                tool_version=diagnostic.tool_version,
                database_versions=diagnostic.database_versions,
                database_manifests=diagnostic.database_manifests,
                capabilities=provider.spec.capabilities,
                issues=diagnostic.issues,
            )
        diagnostics.append(diagnostic)
    return DoctorReport(mode=mode, providers=tuple(diagnostics))
