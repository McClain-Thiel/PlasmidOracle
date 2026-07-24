from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from hashlib import sha256
from pathlib import Path

_SAFE_PREFIX = re.compile(r"[^A-Za-z0-9_.:-]+")
_ID_SCHEMA_VERSION = "1"


def _canonical(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonical(getattr(value, field.name))
            for field in fields(value)
            if field.name not in {"evidence_id", "annotation_id"}
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes | bytearray):
        return [_canonical(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"Stable identifier content is not JSON-compatible: {value!r}")


def stable_digest(value: object) -> str:
    encoded = json.dumps(
        _canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def stable_evidence_id(namespace: str, payload: object) -> str:
    normalized = _SAFE_PREFIX.sub("_", namespace.strip()).strip("._:-") or "evidence"
    digest = stable_digest(
        {
            "id_schema_version": _ID_SCHEMA_VERSION,
            "namespace": normalized,
            "payload": payload,
        }
    )
    return f"{normalized}:{digest[:32]}"
