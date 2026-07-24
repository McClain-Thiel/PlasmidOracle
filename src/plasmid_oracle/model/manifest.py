from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from plasmid_oracle._immutability import freeze_mapping


class ProviderStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    UNAVAILABLE = "unavailable"
    CACHED = "cached"


@dataclass(frozen=True, slots=True)
class ProviderRun:
    name: str
    status: ProviderStatus
    provider_version: str | None = None
    tool_version: str | None = None
    database_versions: Mapping[str, str] = field(default_factory=dict)
    parameters: Mapping[str, object] = field(default_factory=dict)
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
        object.__setattr__(self, "parameters", freeze_mapping(self.parameters))
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
