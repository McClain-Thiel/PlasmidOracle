from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plasmid_oracle.model import ProviderRun


class PlasmidOracleError(Exception):
    """Base exception for Plasmid Oracle."""


class InvalidSequenceError(PlasmidOracleError, ValueError):
    """Raised when DNA cannot be normalized without changing its meaning."""


class InvalidLocationError(PlasmidOracleError, ValueError):
    """Raised when sequence coordinates do not form a valid location."""


class InvalidProviderResultError(PlasmidOracleError, ValueError):
    """Raised when a provider returns evidence outside the canonical contract."""


class InvalidSerializedPlasmidError(PlasmidOracleError, ValueError):
    """Raised when serialized data violates the versioned plasmid schema."""


class ProviderUnavailableError(PlasmidOracleError, RuntimeError):
    """Raised when a provider dependency or database is not installed."""


class ProviderExecutionError(PlasmidOracleError):
    """Raised when a requested provider does not complete."""

    def __init__(
        self,
        provider_name: str,
        provider_runs: Sequence[ProviderRun],
    ) -> None:
        self.provider_name = provider_name
        self.provider_runs = tuple(provider_runs)
        failed_run = next(
            (run for run in reversed(self.provider_runs) if run.name == provider_name),
            self.provider_runs[-1],
        )
        detail = failed_run.error or "unknown provider error"
        super().__init__(f"Provider {provider_name!r} failed: {detail}")
