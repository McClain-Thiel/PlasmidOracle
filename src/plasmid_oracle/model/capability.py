from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from plasmid_oracle._immutability import freeze_mapping


class AbsenceSemantics(StrEnum):
    POSITIVE_ONLY = "positive_only"
    BOUNDED_CATALOG = "bounded_catalog"
    EXHAUSTIVE = "exhaustive"


@dataclass(frozen=True, slots=True)
class ProviderCapability:
    concept: str
    absence_semantics: AbsenceSemantics | str = AbsenceSemantics.POSITIVE_ONLY
    scope: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.concept.strip():
            raise ValueError("Provider capability concept cannot be empty")
        object.__setattr__(self, "absence_semantics", AbsenceSemantics(self.absence_semantics))
        object.__setattr__(self, "scope", freeze_mapping(self.scope))

    @property
    def supports_absence(self) -> bool:
        return self.absence_semantics in {
            AbsenceSemantics.BOUNDED_CATALOG,
            AbsenceSemantics.EXHAUSTIVE,
        }
