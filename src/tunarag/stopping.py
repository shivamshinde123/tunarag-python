"""Composable stop conditions for study execution."""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StopContext:
    """Current study totals supplied to stop conditions."""

    completed_trials: int
    exact_cost: float = 0.0
    estimated_cost: float = 0.0
    elapsed_seconds: float = 0.0

    def __post_init__(self) -> None:
        if self.completed_trials < 0:
            raise ValueError("completed trials must not be negative")
        for name in ("exact_cost", "estimated_cost", "elapsed_seconds"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")


class StopCondition(Protocol):
    """Return whether execution should stop for the current context."""

    def should_stop(self, context: StopContext) -> bool: ...


@dataclass(frozen=True, slots=True)
class MaxTrials:
    """Stop after a maximum number of completed trials."""

    limit: int

    def __post_init__(self) -> None:
        if self.limit < 1:
            raise ValueError("trial limit must be at least one")

    def should_stop(self, context: StopContext) -> bool:
        return context.completed_trials >= self.limit


@dataclass(frozen=True, slots=True)
class CostBudget:
    """Stop when exact cost, or exact plus estimated cost, reaches a budget."""

    limit: float
    count_estimated: bool = True

    def __post_init__(self) -> None:
        if self.limit < 0:
            raise ValueError("cost budget must not be negative")

    def should_stop(self, context: StopContext) -> bool:
        total = context.exact_cost + (context.estimated_cost if self.count_estimated else 0.0)
        return total >= self.limit