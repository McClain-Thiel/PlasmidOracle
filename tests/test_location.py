import pytest

import plasmid_oracle as po


def test_linear_location_uses_one_half_open_span() -> None:
    location = po.Location.from_bounds(
        10,
        25,
        sequence_length=100,
        topology="linear",
        strand="+",
    )

    assert location.spans == (po.Span(10, 25),)
    assert location.length == 15
    assert location.start == 10
    assert location.end == 25
    assert location.wraps_origin is False


def test_circular_location_crossing_origin_uses_two_bounded_spans() -> None:
    location = po.Location.from_bounds(
        90,
        12,
        sequence_length=100,
        topology="circular",
        strand="-",
    )

    assert location.spans == (po.Span(90, 100), po.Span(0, 12))
    assert location.length == 22
    assert location.start == 90
    assert location.end == 12
    assert location.wraps_origin is True
    assert location.strand is po.Strand.REVERSE


def test_linear_location_cannot_wrap() -> None:
    with pytest.raises(po.InvalidLocationError, match="linear"):
        po.Location.from_bounds(
            90,
            12,
            sequence_length=100,
            topology="linear",
        )


@pytest.mark.parametrize(
    ("start", "end", "length"),
    [
        (-1, 5, 100),
        (0, 101, 100),
        (100, 10, 100),
        (4, 4, 100),
        (0, 1, 0),
    ],
)
def test_location_rejects_invalid_or_empty_bounds(start: int, end: int, length: int) -> None:
    with pytest.raises(po.InvalidLocationError):
        po.Location.from_bounds(
            start,
            end,
            sequence_length=length,
            topology="circular",
        )


def test_location_can_end_exactly_at_the_sequence_boundary() -> None:
    location = po.Location.from_bounds(
        75,
        100,
        sequence_length=100,
        topology="circular",
    )

    assert location.spans == (po.Span(75, 100),)
    assert location.wraps_origin is False
