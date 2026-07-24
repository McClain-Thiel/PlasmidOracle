from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any

from platformdirs import user_cache_path

from plasmid_oracle.model import SequenceInfo
from plasmid_oracle.pipeline.diagnostics import ProviderDiagnostic
from plasmid_oracle.pipeline.provider import ProviderContext, ProviderResult, ProviderSpec
from plasmid_oracle.serialization.json import (
    provider_result_from_dict,
    provider_result_to_dict,
)

_CACHE_SCHEMA_VERSION = "1"
_SAFE_COMPONENT = re.compile(r"[^A-Za-z0-9_.-]+")


@dataclass(frozen=True, slots=True)
class CacheLookup:
    result: ProviderResult | None
    warning: str | None = None


def default_cache_dir() -> Path:
    return user_cache_path("plasmid-oracle") / "provider-results"


def _canonical(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_canonical(item) for item in value]
    if value is None or isinstance(value, str | int | float | bool):
        return value
    raise TypeError(f"Cache parameter {value!r} is not JSON-compatible")


def _identity_payload(
    *,
    spec: ProviderSpec,
    sequence: SequenceInfo,
    context: ProviderContext,
    diagnostic: ProviderDiagnostic,
) -> dict[str, object]:
    return {
        "cache_schema_version": _CACHE_SCHEMA_VERSION,
        "sequence_checksum": sequence.checksum,
        "topology": sequence.topology.value,
        "provider": spec.name,
        "provider_version": spec.version,
        "tool_version": diagnostic.tool_version,
        "database_versions": dict(diagnostic.database_versions),
        "parameters": _canonical(context.parameters),
    }


def _digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ProviderCache:
    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.expanduser())

    def key(
        self,
        *,
        spec: ProviderSpec,
        sequence: SequenceInfo,
        context: ProviderContext,
        diagnostic: ProviderDiagnostic,
    ) -> tuple[str, dict[str, object]]:
        identity = _identity_payload(
            spec=spec,
            sequence=sequence,
            context=context,
            diagnostic=diagnostic,
        )
        return _digest(identity), identity

    def path_for(self, *, provider_name: str, digest: str) -> Path:
        component = _SAFE_COMPONENT.sub("_", provider_name).strip("._") or "provider"
        return self.root / component / f"{digest}.json"

    def load(
        self,
        *,
        provider_name: str,
        digest: str,
        identity: Mapping[str, object],
    ) -> CacheLookup:
        path = self.path_for(provider_name=provider_name, digest=digest)
        if not path.exists():
            return CacheLookup(result=None)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("cache document is not an object")
            if payload.get("cache_schema_version") != _CACHE_SCHEMA_VERSION:
                raise ValueError("cache schema version is unsupported")
            if payload.get("identity") != identity:
                raise ValueError("cache identity does not match its path")
            result_payload = payload.get("result")
            if not isinstance(result_payload, dict):
                raise ValueError("cache result is not an object")
            return CacheLookup(result=provider_result_from_dict(result_payload))
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as error:
            return CacheLookup(
                result=None,
                warning=f"Ignored invalid cache entry {path}: {error}",
            )

    def store(
        self,
        *,
        provider_name: str,
        digest: str,
        identity: Mapping[str, object],
        result: ProviderResult,
    ) -> None:
        path = self.path_for(provider_name=provider_name, digest=digest)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "cache_schema_version": _CACHE_SCHEMA_VERSION,
            "identity": dict(identity),
            "result": provider_result_to_dict(result),
        }
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            dir=path.parent,
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
                json.dump(
                    payload,
                    temporary,
                    indent=2,
                    sort_keys=True,
                    allow_nan=False,
                )
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, path)
        except BaseException:
            Path(temporary_name).unlink(missing_ok=True)
            raise
