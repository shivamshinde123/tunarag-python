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
        """Classify known transient failures without parsing messages."""

        if isinstance(error, TunaRAGError):
            return error.retryable
        return isinstance(error, (TimeoutError, asyncio.TimeoutError, ConnectionError))


def _validate_optional_timeout(name: str, value: float | None) -> None:
    if value is not None and (not math.isfinite(value) or value <= 0):
        raise ValueError(f"{name} must be a positive finite number or None")


def _validate_nonnegative_finite(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a nonnegative finite number")
