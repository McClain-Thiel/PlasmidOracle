from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeAlias

from plasmid_oracle._immutability import freeze_mapping

JsonScalar: TypeAlias = str | int | float | bool


class EvaluationStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    WARNING = "warning"
    UNKNOWN = "unknown"


class EvaluationScope(StrEnum):
    VALIDITY = "validity"
    UTILITY = "utility"
    FIDELITY = "fidelity"


@dataclass(frozen=True, slots=True)
class EvaluationConfig:
    min_identity: float = 0.8
    min_coverage: float = 0.8

    def __post_init__(self) -> None:
        if not 0 <= self.min_identity <= 1:
            raise ValueError("min_identity must be a fraction between 0 and 1")
        if not 0 <= self.min_coverage <= 1:
            raise ValueError("min_coverage must be a fraction between 0 and 1")


@dataclass(frozen=True, slots=True)
class Requirement:
    check: str
    value: JsonScalar | None = None
    source_text: str = ""
    confidence: float | None = None
    canonicalization_status: str = "unresolved"
    ambiguities: tuple[str, ...] = ()
    metadata: Mapping[str, JsonScalar | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.check.strip():
            raise ValueError("Requirement check cannot be empty")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("Requirement confidence must be a fraction between 0 and 1")
        if not self.canonicalization_status.strip():
            raise ValueError("Requirement canonicalization status cannot be empty")
        object.__setattr__(self, "ambiguities", tuple(self.ambiguities))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class RequirementSet:
    preset: str | None = None
    requirements: tuple[Requirement, ...] = ()

    def __post_init__(self) -> None:
        if self.preset is not None and not self.preset.strip():
            raise ValueError("Requirement preset cannot be empty")
        object.__setattr__(self, "requirements", tuple(self.requirements))


@dataclass(frozen=True, slots=True)
class EvaluationFinding:
    check: str
    status: EvaluationStatus
    message: str
    evidence_ids: tuple[str, ...] = ()
    required: bool = True
    requirement: Requirement | None = None
    metadata: Mapping[str, JsonScalar | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.check.strip():
            raise ValueError("Evaluation check cannot be empty")
        if not self.message.strip():
            raise ValueError("Evaluation finding message cannot be empty")
        object.__setattr__(self, "status", EvaluationStatus(self.status))
        object.__setattr__(self, "evidence_ids", tuple(sorted(set(self.evidence_ids))))
        object.__setattr__(self, "metadata", freeze_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    scope: EvaluationScope
    status: EvaluationStatus
    preset: str | None
    findings: tuple[EvaluationFinding, ...]
    requirements: RequirementSet | None = None
    config: EvaluationConfig = field(default_factory=EvaluationConfig)

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", EvaluationScope(self.scope))
        object.__setattr__(self, "status", EvaluationStatus(self.status))
        if self.preset is not None and not self.preset.strip():
            raise ValueError("Evaluation preset cannot be empty")
        object.__setattr__(self, "findings", tuple(self.findings))

    def finding(self, check: str) -> EvaluationFinding:
        normalized = check.strip().casefold()
        if not normalized:
            raise ValueError("Evaluation check query cannot be empty")
        for finding in self.findings:
            if finding.check.casefold() == normalized:
                return finding
        raise KeyError(check)

    def to_dict(self) -> dict[str, object]:
        return {
            "scope": self.scope.value,
            "status": self.status.value,
            "preset": self.preset,
            "findings": [
                {
                    "check": finding.check,
                    "status": finding.status.value,
                    "message": finding.message,
                    "evidence_ids": list(finding.evidence_ids),
                    "required": finding.required,
                    "requirement": _requirement_value(finding.requirement),
                    "metadata": dict(finding.metadata),
                }
                for finding in self.findings
            ],
            "requirements": _requirement_set_value(self.requirements),
            "config": {
                "min_identity": self.config.min_identity,
                "min_coverage": self.config.min_coverage,
            },
        }


def _requirement_value(requirement: Requirement | None) -> dict[str, object] | None:
    if requirement is None:
        return None
    return {
        "check": requirement.check,
        "value": requirement.value,
        "source_text": requirement.source_text,
        "confidence": requirement.confidence,
        "canonicalization_status": requirement.canonicalization_status,
        "ambiguities": list(requirement.ambiguities),
        "metadata": dict(requirement.metadata),
    }


def _requirement_set_value(requirements: RequirementSet | None) -> dict[str, object] | None:
    if requirements is None:
        return None
    requirement_values: list[dict[str, object]] = []
    for requirement in requirements.requirements:
        value = _requirement_value(requirement)
        if value is not None:
            requirement_values.append(value)
    return {
        "preset": requirements.preset,
        "requirements": requirement_values,
    }
