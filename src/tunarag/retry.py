"""Deterministic retry and timeout policy."""

import asyncio
import math
from dataclasses import dataclass

from .errors import TunaRAGError


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Bound retries, exponential backoff, and execution timeouts."""

    max_retries: int = 2
    sample_timeout_seconds: float | None = 60.0
    trial_timeout_seconds: float | None = 300.0
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.max_retries, int)
            or isinstance(self.max_retries, bool)
            or self.max_retries < 0
        ):
            raise ValueError("max_retries must be a nonnegative integer")
        _validate_optional_timeout("sample timeout", self.sample_timeout_seconds)
        _validate_optional_timeout("trial timeout", self.trial_timeout_seconds)
        _validate_nonnegative_finite("base retry delay", self.base_delay_seconds)
        _validate_nonnegative_finite("maximum retry delay", self.max_delay_seconds)
        if self.base_delay_seconds > self.max_delay_seconds:
            raise ValueError("base retry delay must not exceed maximum retry delay")

    @property
    def max_attempts(self) -> int:
        """Return the initial attempt plus configured retries."""

        return self.max_retries + 1

    @property
    def lease_seconds(self) -> float:
        """Return a recovery lease longer than the configured trial timeout."""

        return 86_400.0 if self.trial_timeout_seconds is None else self.trial_timeout_seconds + 60.0

    def delay_before_retry(self, failed_attempt_number: int) -> float:
        """Return deterministic capped exponential backoff."""

        if failed_attempt_number < 0:
            raise ValueError("failed attempt number must not be negative")
        return float(
            min(self.base_delay_seconds * (2**failed_attempt_number), self.max_delay_seconds)
        )

    def is_retryable(self, error: BaseException) -> bool:
        """Classify known transient failures without parsing messages.

        Besides Python's own timeout/connection errors, this recognizes provider SDK
        failures (OpenAI, httpx, LiteLLM, Google GenAI, Anthropic, ...) by exception type
        name or HTTP status, without importing those SDKs: timeouts, dropped connections,
        rate limits (429), and transient server errors (408, 5xx). Wrapped causes count.
        """

        current: BaseException | None = error
        for _ in range(5):  # follow explicit `raise ... from` chains a few levels
            if current is None:
                return False
            if isinstance(current, TunaRAGError):
                if current.retryable:
                    return True
            elif _is_transient(current):
                return True
            current = current.__cause__
        return False


_TRANSIENT_TYPE_NAMES = frozenset(
    {
        "APITimeoutError",
        "APIConnectionError",
        "RateLimitError",
        "InternalServerError",
        "ServiceUnavailableError",
        "Timeout",
        "TimeoutException",
        "TransportError",
        "NetworkError",
        "ConnectError",
        "ReadError",
        "RemoteProtocolError",
    }
)
_TRANSIENT_STATUS_CODES = frozenset({408, 425, 429, 500, 502, 503, 504, 529})


def _is_transient(error: BaseException) -> bool:
    if isinstance(error, (TimeoutError, asyncio.TimeoutError, ConnectionError)):
        return True
    if any(cls.__name__ in _TRANSIENT_TYPE_NAMES for cls in type(error).__mro__):
        return True
    for attribute in ("status_code", "code", "status"):
        value = getattr(error, attribute, None)
        if isinstance(value, int) and not isinstance(value, bool):
            return value in _TRANSIENT_STATUS_CODES
    return False


def _validate_optional_timeout(name: str, value: float | None) -> None:
    if value is not None and (not math.isfinite(value) or value <= 0):
        raise ValueError(f"{name} must be a positive finite number or None")


def _validate_nonnegative_finite(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a nonnegative finite number")
