from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from plasmid_oracle._immutability import freeze_mapping
from plasmid_oracle.model.capability import ProviderCapability
from plasmid_oracle.model.identifiers import stable_digest


class ProviderStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"
    CACHED = "cached"


@dataclass(frozen=True, slots=True)
class DatabaseIdentity:
    database: str
    version: str | None = None
    manifest_sha256: str | None = None
    identity: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.database.strip():
            raise ValueError("Database identity name cannot be empty")
        object.__setattr__(self, "identity", freeze_mapping(self.identity))
        manifest_sha256 = self.manifest_sha256 or stable_digest(
            {
                "database": self.database,
                "version": self.version,
                "identity": self.identity,
            }
        )
        object.__setattr__(self, "manifest_sha256", manifest_sha256)


def database_identities_from_versions(
    database_versions: Mapping[str, str],
) -> tuple[DatabaseIdentity, ...]:
    return tuple(
        DatabaseIdentity(
            database=database,
            version=version,
            identity={"reported_version": version},
        )
        for database, version in sorted(database_versions.items())
    )


@dataclass(frozen=True, slots=True)
class ProviderRun:
    name: str
    status: ProviderStatus
    provider_version: str | None = None
    tool_version: str | None = None
    database_versions: Mapping[str, str] = field(default_factory=dict)
    database_manifests: tuple[DatabaseIdentity, ...] = ()
    capabilities: tuple[ProviderCapability, ...] = ()
    parameters: Mapping[str, object] = field(default_factory=dict)
    diagnostic_identity: Mapping[str, object] = field(default_factory=dict)
    cache_key: str | None = None
    runtime_seconds: float = 0.0
    warnings: tuple[str, ...] = ()
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Provider run name cannot be empty")
        if self.runtime_seconds < 0:
            raise ValueError("Provider runtime cannot be negative")
        object.__setattr__(self, "status", ProviderStatus(self.status))
        object.__setattr__(self, "database_versions", freeze_mapping(self.database_versions))
        database_manifests = (
            tuple(self.database_manifests)
            if self.database_manifests
            else database_identities_from_versions(self.database_versions)
        )
        object.__setattr__(self, "database_manifests", database_manifests)
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(self, "parameters", freeze_mapping(self.parameters))
        object.__setattr__(self, "diagnostic_identity", freeze_mapping(self.diagnostic_identity))
        object.__setattr__(self, "warnings", tuple(self.warnings))


@dataclass(frozen=True, slots=True)
class AnalysisManifest:
    pipeline_version: str
    mode: str
    provider_runs: tuple[ProviderRun, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_runs", tuple(self.provider_runs))
        object.__setattr__(self, "warnings", tuple(self.warnings))
