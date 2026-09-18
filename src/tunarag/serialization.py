"""Canonical, secret-safe serialization for identity and cache keys."""

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any, cast

from .domain import Secret


def canonicalize(value: Any) -> Any:
    """Convert supported values to deterministic JSON-compatible structures."""

    if isinstance(value, Secret):
        return {"__secret__": True}
    if is_dataclass(value):
        return canonicalize(asdict(cast(Any, value)))
    if isinstance(value, Mapping):
        return {
            str(key): canonicalize(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
            if not isinstance(item, Secret)
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [canonicalize(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("nonfinite numbers are not supported")
        return format(value, ".15g")
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    """Serialize a value using stable key ordering and schema-independent JSON."""

    return json.dumps(
        canonicalize(value), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def content_hash(value: Any, *, namespace: str = "autorag-tuner:v1") -> str:
    """Return a stable SHA-256 digest for a canonical value."""

    return hashlib.sha256(namespace.encode() + b"\0" + canonical_json(value)).hexdigest()