from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256

from plasmid_oracle.errors import InvalidSequenceError

_IUPAC_DNA = frozenset("ACGTRYSWKMBDHVN")
_UNAMBIGUOUS_DNA = frozenset("ACGT")
_COMPLEMENT = str.maketrans(
    {
        "A": "T",
        "C": "G",
        "G": "C",
        "T": "A",
        "R": "Y",
        "Y": "R",
        "S": "S",
        "W": "W",
        "K": "M",
        "M": "K",
        "B": "V",
        "D": "H",
        "H": "D",
        "V": "B",
        "N": "N",
    }
)


class Topology(StrEnum):
    LINEAR = "linear"
    CIRCULAR = "circular"


@dataclass(frozen=True, slots=True)
class SequenceWarning:
    code: str
    message: str


def _normalize_bases(raw: str) -> str:
    if not isinstance(raw, str):
        raise InvalidSequenceError("DNA sequence must be a string")

    normalized = "".join(character for character in raw.upper() if not character.isspace())
    if not normalized:
        raise InvalidSequenceError("DNA sequence is empty after removing whitespace")

    invalid = sorted(set(normalized) - _IUPAC_DNA)
    if invalid:
        rendered = ", ".join(repr(character) for character in invalid)
        raise InvalidSequenceError(f"Invalid DNA character(s): {rendered}")
    return normalized


def reverse_complement(sequence: str) -> str:
    return sequence.translate(_COMPLEMENT)[::-1]


def _minimal_rotation(sequence: str) -> str:
    """Return the lexicographically minimal rotation using Booth's algorithm."""
    if not sequence:
        return sequence

    doubled = sequence + sequence
    length = len(sequence)
    left = 0
    right = 1
    offset = 0

    while left < length and right < length and offset < length:
        left_base = doubled[left + offset]
        right_base = doubled[right + offset]
        if left_base == right_base:
            offset += 1
            continue

        if left_base > right_base:
            left = left + offset + 1
            if left <= right:
                left = right + 1
        else:
            right = right + offset + 1
            if right <= left:
                right = left + 1
        offset = 0

    start = min(left, right)
    return doubled[start : start + length]


def _digest(sequence: str) -> str:
    return sha256(sequence.encode("ascii")).hexdigest()


@dataclass(frozen=True, slots=True)
class SequenceInfo:
    bases: str
    topology: Topology = Topology.CIRCULAR
    checksum: str = field(init=False)
    canonical_checksum: str = field(init=False)
    ambiguous_base_count: int = field(init=False)
    gc_fraction: float | None = field(init=False)
    warnings: tuple[SequenceWarning, ...] = field(init=False)

    def __post_init__(self) -> None:
        normalized = _normalize_bases(self.bases)
        try:
            topology = Topology(self.topology)
        except ValueError as error:
            raise InvalidSequenceError(f"Unsupported topology: {self.topology!r}") from error

        reverse = reverse_complement(normalized)
        if topology is Topology.CIRCULAR:
            canonical = min(_minimal_rotation(normalized), _minimal_rotation(reverse))
        else:
            canonical = min(normalized, reverse)

        concrete_bases = [base for base in normalized if base in _UNAMBIGUOUS_DNA]
        gc_count = sum(base in {"G", "C"} for base in concrete_bases)
        gc_fraction = gc_count / len(concrete_bases) if concrete_bases else None
        ambiguous_count = len(normalized) - len(concrete_bases)
        warnings: tuple[SequenceWarning, ...] = ()
        if ambiguous_count:
            warnings = (
                SequenceWarning(
                    code="ambiguous_bases",
                    message=f"Sequence contains {ambiguous_count} ambiguous IUPAC base(s)",
                ),
            )

        object.__setattr__(self, "bases", normalized)
        object.__setattr__(self, "topology", topology)
        object.__setattr__(self, "checksum", _digest(normalized))
        object.__setattr__(self, "canonical_checksum", _digest(canonical))
        object.__setattr__(self, "ambiguous_base_count", ambiguous_count)
        object.__setattr__(self, "gc_fraction", gc_fraction)
        object.__setattr__(self, "warnings", warnings)

    @classmethod
    def from_raw(
        cls,
        sequence: str,
        topology: Topology | str = Topology.CIRCULAR,
    ) -> SequenceInfo:
        return cls(bases=sequence, topology=Topology(topology))

    @property
    def length(self) -> int:
        return len(self.bases)
