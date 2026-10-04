"""Immutable domain values shared by the package contracts."""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any


class ValueStatus(str, Enum):
    """Confidence state for an observed or derived value."""

    EXACT = "exact"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class Secret:
    """A value whose contents are never exposed by representation or hashing."""

    value: str

    def __repr__(self) -> str:
        return "Secret(***redacted***)"

    def __str__(self) -> str:
        return "***redacted***"


@dataclass(frozen=True, slots=True)
class MetricValue:
    """A metric observation with its coverage and confidence state."""

    name: str
    value: float | None
    status: ValueStatus = ValueStatus.EXACT
    coverage: float = 1.0

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("metric name must not be empty")
        if not 0.0 <= self.coverage <= 1.0:
            raise ValueError("metric coverage must be between 0 and 1")
        if self.value is not None and not isinstance(self.value, (int, float)):
            raise TypeError("metric value must be numeric or None")


@dataclass(frozen=True, slots=True)
class UsageRecord:
    """Usage observed for one component of a trial."""

    component: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost: float | None = None
    latency_seconds: float | None = None
    status: ValueStatus = ValueStatus.EXACT
    pricing_version: str | None = None

    def __post_init__(self) -> None:
        if not self.component.strip():
            raise ValueError("usage component must not be empty")
        for name in ("input_tokens", "output_tokens"):
            token_value: Any = getattr(self, name)
            if token_value is not None and token_value < 0:
                raise ValueError(f"{name} must not be negative")
        for name in ("cost", "latency_seconds"):
            usage_value: Any = getattr(self, name)
            if usage_value is not None and usage_value < 0:
                raise ValueError(f"{name} must not be negative")


@dataclass(frozen=True, slots=True)
class Candidate:
    """A typed candidate configuration proposed for a trial."""

    parameters: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not self.parameters:
            raise ValueError("candidate parameters must not be empty")
        if any(not name.strip() for name in self.parameters):
            raise ValueError("candidate parameter names must not be empty")
