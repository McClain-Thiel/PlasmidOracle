from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from plasmid_oracle._immutability import freeze_mapping
from plasmid_oracle.model import Annotation, Characterization, SequenceInfo


@dataclass(frozen=True, slots=True)
class ProviderSpec:
    name: str
    version: str
    modes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Provider name cannot be empty")
        if not self.version.strip():
            raise ValueError("Provider version cannot be empty")
        if not self.modes:
            raise ValueError("Provider must support at least one mode")
        object.__setattr__(self, "modes", tuple(self.modes))


@dataclass(frozen=True, slots=True)
class ProviderContext:
    mode: str
    threads: int = 1
    timeout_seconds: float = 600.0
    parameters: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.threads < 1:
            raise ValueError("Provider thread count must be at least 1")
        if self.timeout_seconds <= 0:
            raise ValueError("Provider timeout must be positive")
        object.__setattr__(self, "parameters", freeze_mapping(self.parameters))


@dataclass(frozen=True, slots=True)
class ProviderResult:
    annotations: tuple[Annotation, ...] = ()
    characterization: Characterization = field(default_factory=Characterization)
    tool_version: str | None = None
    database_versions: Mapping[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "annotations", tuple(self.annotations))
        object.__setattr__(self, "database_versions", freeze_mapping(self.database_versions))
        object.__setattr__(self, "warnings", tuple(self.warnings))


class AnnotationProvider(Protocol):
    spec: ProviderSpec

    def run(
        self,
        sequence: SequenceInfo,
        context: ProviderContext,
    ) -> ProviderResult: ...
