from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_MISSING_VALUES = frozenset({"", "-", "NA", "N/A", "NONE", "NULL"})


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    rendered = str(value).strip()
    if rendered.upper() in _MISSING_VALUES:
        return None
    return rendered


def first_text(row: Mapping[str, object], *names: str) -> str | None:
    for name in names:
        value = clean_text(row.get(name))
        if value is not None:
            return value
    return None


def required_int(row: Mapping[str, object], *names: str) -> int:
    value = first_text(row, *names)
    if value is None:
        joined = ", ".join(names)
        raise ValueError(f"Missing required integer field: {joined}")
    return int(float(value))


def optional_float(row: Mapping[str, object], *names: str) -> float | None:
    value = first_text(row, *names)
    if value is None:
        return None
    return float(value.rstrip("%"))


def fraction_from_percent(row: Mapping[str, object], *names: str) -> float | None:
    value = optional_float(row, *names)
    if value is None:
        return None
    fraction = value / 100
    return min(max(fraction, 0.0), 1.0)


def split_values(value: object) -> tuple[str, ...]:
    rendered = clean_text(value)
    if rendered is None:
        return ()
    return tuple(item.strip() for item in rendered.split(",") if clean_text(item) is not None)


def clean_qualifiers(row: Mapping[str, Any]) -> dict[str, object]:
    return {str(key): value for key, value in row.items() if clean_text(value) is not None}
