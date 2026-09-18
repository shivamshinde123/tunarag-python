"""Objective aggregation for quality, cost, and latency metrics."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

from .domain import MetricValue, ValueStatus


class ObjectiveDirection(str, Enum):
    """Whether larger or smaller metric values are beneficial."""

    MAXIMIZE = "maximize"
    MINIMIZE = "minimize"


@dataclass(frozen=True, slots=True)
class ObjectiveTerm:
    """One weighted metric contribution to an objective score."""

    metric: str
    weight: float = 1.0
    direction: ObjectiveDirection = ObjectiveDirection.MAXIMIZE
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        if not self.metric.strip():
            raise ValueError("objective metric must not be empty")
        if self.weight < 0:
            raise ValueError("objective weight must not be negative")
        if self.minimum is not None and self.maximum is not None and self.minimum >= self.maximum:
            raise ValueError("objective minimum must be less than maximum")
        if (self.minimum is None) != (self.maximum is None):
            raise ValueError("objective minimum and maximum must be provided together")


@dataclass(frozen=True, slots=True)
class ObjectiveResult:
    """Aggregated score and confidence state."""

    score: float | None
    status: ValueStatus


@dataclass(frozen=True, slots=True)
class Objective:
    """Combine metric observations into a benefit-oriented weighted score."""

    terms: tuple[ObjectiveTerm, ...]

    def __post_init__(self) -> None:
        if not self.terms:
            raise ValueError("objective must contain at least one term")
        if sum(term.weight for term in self.terms) == 0:
            raise ValueError("objective must contain a positive weight")

    def evaluate(self, metrics: Sequence[MetricValue]) -> ObjectiveResult:
        by_name = {metric.name: metric for metric in metrics}
        score = 0.0
        status = ValueStatus.EXACT
        for term in self.terms:
            metric = by_name.get(term.metric)
            if metric is None or metric.value is None:
                return ObjectiveResult(None, ValueStatus.UNAVAILABLE)
            value = float(metric.value)
            if term.minimum is not None and term.maximum is not None:
                value = (value - term.minimum) / (term.maximum - term.minimum)
                value = max(0.0, min(1.0, value))
            if term.direction is ObjectiveDirection.MINIMIZE:
                value = 1.0 - value if term.minimum is not None else -value
            score += term.weight * value
            if metric.status is ValueStatus.ESTIMATED:
                status = ValueStatus.ESTIMATED
        return ObjectiveResult(score, status)