"""Structured public errors with secret-safe diagnostic details."""

from collections.abc import Mapping, Sequence
from dataclasses import fields, is_dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, cast

from .domain import Secret

_SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "credential",
    "credentials",
    "password",
    "refresh_token",
    "secret",
    "token",
}
_REDACTED = "***redacted***"


class ErrorCode(str, Enum):
    """Stable machine-readable error identifiers."""

    CONFIGURATION = "configuration.invalid"
    SEARCH_SPACE = "search_space.invalid"
    ADAPTER = "adapter.failed"
    EVALUATION = "evaluation.failed"
    STORE = "store.failed"
    RESUME = "resume.incompatible"
    BUDGET = "budget.exhausted"
    OPTIONAL_DEPENDENCY = "dependency.optional_missing"
    SYNC_IN_ASYNC = "runtime.sync_in_async"


class TunaRAGError(Exception):
    """Base class for public package errors."""

    code = ErrorCode.CONFIGURATION

    def __init__(
        self,
        message: str,
        *,
        stage: str | None = None,
        retryable: bool = False,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        if not message.strip():
            raise ValueError("error message must not be empty")
        if stage is not None and not stage.strip():
            raise ValueError("error stage must not be empty")
        self.message = message
        self.stage = stage
        self.retryable = retryable
        safe_details = cast(dict[str, Any], redact(details or {}))
        self.details: Mapping[str, Any] = MappingProxyType(safe_details)
        super().__init__(message)

    def as_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible diagnostic representation."""

        return {
            "code": self.code.value,
            "message": self.message,
            "stage": self.stage,
            "retryable": self.retryable,
            "details": dict(self.details),
        }


class ConfigurationError(TunaRAGError):
    """Configuration could not be parsed or validated."""

    code = ErrorCode.CONFIGURATION


class SearchSpaceError(TunaRAGError):
    """A search-space definition or candidate is invalid."""

    code = ErrorCode.SEARCH_SPACE


class AdapterError(TunaRAGError):
    """The user-owned RAG adapter failed."""

    code = ErrorCode.ADAPTER


class EvaluationError(TunaRAGError):
    """An evaluator failed or returned invalid observations."""

    code = ErrorCode.EVALUATION


class StoreError(TunaRAGError):
    """Durable state could not be read or written."""

    code = ErrorCode.STORE


class ResumeError(TunaRAGError):
    """A study cannot resume under the supplied semantics."""

    code = ErrorCode.RESUME


class BudgetError(TunaRAGError):
    """A configured scheduling budget has been exhausted."""

    code = ErrorCode.BUDGET


class MissingOptionalDependencyError(TunaRAGError):
    """A requested integration extra is not installed."""

    code = ErrorCode.OPTIONAL_DEPENDENCY

    def __init__(self, feature: str, extra: str) -> None:
        if not feature.strip() or not extra.strip():
            raise ValueError("feature and extra must not be empty")
        super().__init__(
            f"{feature} requires the optional '{extra}' extra",
            stage="dependency",
            details={"feature": feature, "extra": extra},
        )


class SyncInAsyncContextError(TunaRAGError):
    """A synchronous entry point was called from an active event loop."""

    code = ErrorCode.SYNC_IN_ASYNC

    def __init__(self) -> None:
        super().__init__(
            "the synchronous API cannot run inside an active event loop; use the async API",
            stage="runtime",
        )


def redact(value: Any, *, key: str | None = None) -> Any:
    """Return a recursively redacted, JSON-compatible diagnostic value."""

    if key is not None and _is_sensitive_key(key):
        return _REDACTED
    if isinstance(value, Secret):
        return _REDACTED
    if is_dataclass(value):
        return {
            field.name: redact(getattr(value, field.name), key=field.name)
            for field in fields(cast(Any, value))
        }
    if isinstance(value, Mapping):
        return {str(item_key): redact(item, key=str(item_key)) for item_key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [redact(item) for item in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    return f"<{type(value).__name__}>"


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith(
        ("_api_key", "_credential", "_password", "_secret", "_token")
    )
