from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, cast


def freeze_value(value: Any) -> Any:
    """Recursively freeze common mutable container values."""
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze_value(item) for key, item in value.items()})
    if isinstance(value, list | tuple):
        return tuple(freeze_value(item) for item in value)
    if isinstance(value, set | frozenset):
        return frozenset(freeze_value(item) for item in value)
    return value


def freeze_mapping(value: Mapping[str, object] | None) -> Mapping[str, object]:
    if value is None:
        return MappingProxyType({})
    return cast(Mapping[str, object], freeze_value(value))
