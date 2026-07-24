from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from plasmid_oracle.errors import InvalidLocationError
from plasmid_oracle.model.sequence import Topology


class Strand(StrEnum):
    FORWARD = "+"
    REVERSE = "-"
    UNKNOWN = "."


@dataclass(frozen=True, slots=True, order=True)
class Span:
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.start < 0:
            raise InvalidLocationError("Span start cannot be negative")
        if self.end <= self.start:
            raise InvalidLocationError("Span must have positive length")

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class Location:
    spans: tuple[Span, ...]
    sequence_length: int
    strand: Strand = Strand.UNKNOWN

    def __post_init__(self) -> None:
        spans = tuple(self.spans)
        if self.sequence_length <= 0:
            raise InvalidLocationError("Sequence length must be positive")
        if not 1 <= len(spans) <= 2:
            raise InvalidLocationError("A location must contain one or two spans")
        if any(span.end > self.sequence_length for span in spans):
            raise InvalidLocationError("Location exceeds the sequence boundary")
        if len(spans) == 2:
            first, second = spans
            if first.end != self.sequence_length or second.start != 0:
                raise InvalidLocationError("A wrapped location must meet the sequence origin")
            if first.start <= second.end:
                raise InvalidLocationError("A wrapped location cannot exceed one sequence length")

        try:
            strand = Strand(self.strand)
        except ValueError as error:
            raise InvalidLocationError(f"Unsupported strand: {self.strand!r}") from error

        object.__setattr__(self, "spans", spans)
        object.__setattr__(self, "strand", strand)

    @classmethod
    def from_bounds(
        cls,
        start: int,
        end: int,
        *,
        sequence_length: int,
        topology: Topology | str,
        strand: Strand | str = Strand.UNKNOWN,
    ) -> Location:
        if sequence_length <= 0:
            raise InvalidLocationError("Sequence length must be positive")
        if start < 0 or start >= sequence_length:
            raise InvalidLocationError("Location start is outside the sequence")
        if end < 0 or end > sequence_length:
            raise InvalidLocationError("Location end is outside the sequence")
        if start == end:
            raise InvalidLocationError("Location cannot be empty")

        try:
            normalized_topology = Topology(topology)
        except ValueError as error:
            raise InvalidLocationError(f"Unsupported topology: {topology!r}") from error

        spans: tuple[Span, ...]
        if start < end:
            spans = (Span(start, end),)
        elif normalized_topology is Topology.LINEAR:
            raise InvalidLocationError("A linear location cannot wrap around the origin")
        else:
            spans = (Span(start, sequence_length),)
            if end > 0:
                spans += (Span(0, end),)

        return cls(
            spans=spans,
            sequence_length=sequence_length,
            strand=Strand(strand),
        )

    @property
    def length(self) -> int:
        return sum(span.length for span in self.spans)

    @property
    def start(self) -> int:
        return self.spans[0].start

    @property
    def end(self) -> int:
        return self.spans[-1].end

    @property
    def wraps_origin(self) -> bool:
        return len(self.spans) == 2
