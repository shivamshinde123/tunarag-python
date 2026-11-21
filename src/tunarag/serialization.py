"""Canonical, secret-safe serialization for identity and cache keys."""

import functools
import hashlib
import inspect
import json
import math
import textwrap
import types
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
        # Tagged so the float 0.5 and the string "0.5" never hash identically.
        return {"__float__": format(value, ".15g")}
    if value is None or isinstance(value, (bool, int, str)):
        return value
    describe = getattr(value, "describe", None)
    if callable(describe):
        # Custom search-space parameters (sample/accepts/describe) identify by description.
        value_type = type(value)
        return {
            "__type__": f"{value_type.__module__}.{value_type.__qualname__}",
            "describe": canonicalize(describe()),
        }
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    """Serialize a value using stable key ordering and schema-independent JSON."""

    return json.dumps(
        canonicalize(value), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def storage_json(value: Any) -> bytes:
    """Serialize supported values reversibly while omitting mapping secrets."""

    return json.dumps(
        _storage_value(value), ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")


def content_hash(value: Any, *, namespace: str = "autorag-tuner:v1") -> str:
    """Return a stable SHA-256 digest for a canonical value."""

    return hashlib.sha256(namespace.encode() + b"\0" + canonical_json(value)).hexdigest()


def callable_identity(function: Any, *, _depth: int = 0) -> Any:
    """Return a stable identity for a callable that changes when its behavior changes.

    Uses the qualified name plus a digest of the function's code, closure values, and
    defaults. Two different lambdas, or an edited function body, therefore get different
    identities. Named functions hash their source text (stable across Python versions);
    lambdas hash their own bytecode, because a lambda's "source" is the whole surrounding
    line. Paths and line numbers are not included, so moving a project does not invalidate
    caches or resumable studies.
    """

    if function is None:
        return None
    if _depth > 3:
        return f"<{type(function).__qualname__}>"
    if isinstance(function, functools.partial):
        return {
            "partial": callable_identity(function.func, _depth=_depth + 1),
            "args": _safe_canonical(function.args),
            "keywords": _safe_canonical(function.keywords),
        }
    name = getattr(function, "__qualname__", None) or type(function).__qualname__
    module = getattr(function, "__module__", None) or type(function).__module__
    identity: dict[str, Any] = {"name": f"{module}.{name}"}
    code = getattr(getattr(function, "__func__", function), "__code__", None)
    if isinstance(code, types.CodeType):
        try:
            if code.co_name == "<lambda>":
                raise TypeError("lambda source is the enclosing line")
            text = textwrap.dedent(inspect.getsource(function))
            identity["source"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        except (OSError, TypeError):
            identity["bytecode"] = _code_digest(code)
        closure = getattr(function, "__closure__", None) or ()
        if closure:
            identity["closure"] = [_safe_cell(cell, _depth + 1) for cell in closure]
        defaults = getattr(function, "__defaults__", None)
        if defaults:
            identity["defaults"] = _safe_canonical(defaults)
    else:
        fingerprint = getattr(function, "fingerprint", None)
        if callable(fingerprint):
            identity["fingerprint"] = _safe_canonical(fingerprint())
    return identity


def callable_name(function: Any) -> str | None:
    """Return only a callable's qualified name (used when an explicit identity is given)."""

    if function is None:
        return None
    if isinstance(function, functools.partial):
        return callable_name(function.func)
    name = getattr(function, "__qualname__", None) or type(function).__qualname__
    module = getattr(function, "__module__", None) or type(function).__module__
    return f"{module}.{name}"


def _code_digest(code: types.CodeType) -> str:
    digest = hashlib.sha256(code.co_code)
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            digest.update(_code_digest(constant).encode())
        else:
            digest.update(repr(constant).encode())
    digest.update(repr((code.co_names, code.co_varnames, code.co_freevars)).encode())
    return digest.hexdigest()


def _safe_cell(cell: Any, depth: int) -> Any:
    try:
        contents = cell.cell_contents
    except ValueError:  # empty cell
        return None
    if callable(contents) and not isinstance(contents, type):
        return callable_identity(contents, _depth=depth)
    return _safe_canonical(contents)


def _safe_canonical(value: Any) -> Any:
    try:
        return canonicalize(value)
    except (TypeError, ValueError):
        return f"<{type(value).__module__}.{type(value).__qualname__}>"


def _storage_value(value: Any) -> Any:
    if isinstance(value, Secret):
        return {"__secret__": True}
    if is_dataclass(value):
        return _storage_value(asdict(cast(Any, value)))
    if isinstance(value, Mapping):
        return {
            str(key): _storage_value(item)
            for key, item in sorted(value.items(), key=lambda entry: str(entry[0]))
            if not isinstance(item, Secret)
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_storage_value(item) for item in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("nonfinite numbers are not supported")
        return value
    if value is None or isinstance(value, (bool, int, str)):
        return value
    raise TypeError(f"unsupported storage value: {type(value).__name__}")
