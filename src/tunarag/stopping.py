"""Composable stop conditions for study execution."""

import math
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class StopContext:
    """Current study totals supplied to stop conditions."""

    completed_trials: int
    exact_cost: float = 0.0
    estimated_cost: float = 0.0
    elapsed_seconds: float = 0.0
    successful_trials: int = 0
    failed_trials: int = 0
    objective_scores: tuple[float | None, ...] = ()

    def __post_init__(self) -> None:
        if (
            isinstance(self.completed_trials, bool)
            or not isinstance(self.completed_trials, int)
            or self.completed_trials < 0
        ):
            raise ValueError("completed trials must not be negative")
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in (self.successful_trials, self.failed_trials)
        ):
            raise ValueError("trial status counts must not be negative")
        if self.successful_trials + self.failed_trials > self.completed_trials:
            raise ValueError("trial status counts exceed completed trials")
        if self.objective_scores and len(self.objective_scores) != self.completed_trials:
            raise ValueError("objective score history must match completed trials")
        for name in ("exact_cost", "estimated_cost", "elapsed_seconds"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        if any(score is not None and not math.isfinite(score) for score in self.objective_scores):
            raise ValueError("objective scores must be finite or None")


class StopCondition(Protocol):
    """Return whether execution should stop for the current context."""

    def should_stop(self, context: StopContext) -> bool: ...


@dataclass(frozen=True, slots=True)
class MaxTrials:
    """Stop after a maximum number of completed trials."""

    limit: int

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit < 1:
            raise ValueError("trial limit must be at least one")

    def should_stop(self, context: StopContext) -> bool:
        return context.completed_trials >= self.limit

    def fingerprint(self) -> object:
        return {"limit": self.limit}


@dataclass(frozen=True, slots=True)
class CostBudget:
    """Stop when exact cost, or exact plus estimated cost, reaches a budget."""

    limit: float
    count_estimated: bool = True

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not math.isfinite(self.limit) or self.limit < 0:
            raise ValueError("cost budget must be finite and nonnegative")
        if not isinstance(self.count_estimated, bool):
            raise TypeError("count_estimated must be a boolean")

    def should_stop(self, context: StopContext) -> bool:
        total = context.exact_cost + (context.estimated_cost if self.count_estimated else 0.0)
        return total >= self.limit

    def fingerprint(self) -> object:
        return {"limit": self.limit, "count_estimated": self.count_estimated}


@dataclass(frozen=True, slots=True)
class TimeBudget:
    """Stop when elapsed wall-clock execution reaches a limit."""

    seconds: float

    def __post_init__(self) -> None:
        if isinstance(self.seconds, bool) or not math.isfinite(self.seconds) or self.seconds < 0:
            raise ValueError("time budget must be finite and nonnegative")

    def should_stop(self, context: StopContext) -> bool:
        return context.elapsed_seconds >= self.seconds

    def fingerprint(self) -> object:
        return {"seconds": self.seconds}


@dataclass(frozen=True, slots=True)
class TargetScore:
    """Stop when any successful objective reaches a benefit-oriented target."""

    target: float

    def __post_init__(self) -> None:
        if isinstance(self.target, bool) or not math.isfinite(self.target):
            raise ValueError("target score must be finite")

    def should_stop(self, context: StopContext) -> bool:
        return any(score is not None and score >= self.target for score in context.objective_scores)

    def fingerprint(self) -> object:
        return {"target": self.target}


@dataclass(frozen=True, slots=True)
class MaxFailures:
    """Stop after a total or consecutive number of failed trials."""

    limit: int
    consecutive: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit < 1:
            raise ValueError("failure limit must be a positive integer")

    def should_stop(self, context: StopContext) -> bool:
        if not self.consecutive:
            return context.failed_trials >= self.limit
        failures = 0
        for score in reversed(context.objective_scores):
            if score is not None:
                break
            failures += 1
        return failures >= self.limit

    def fingerprint(self) -> object:
        return {"limit": self.limit, "consecutive": self.consecutive}


@dataclass(frozen=True, slots=True)
class NoImprovement:
    """Stop after completed trials fail to improve the best objective."""

    patience: int
    min_delta: float = 0.0
    warmup_trials: int = 1

    def __post_init__(self) -> None:
        if (
            isinstance(self.patience, bool)
            or not isinstance(self.patience, int)
            or self.patience < 1
        ):
            raise ValueError("no-improvement patience must be a positive integer")
        if (
            isinstance(self.min_delta, bool)
            or not math.isfinite(self.min_delta)
            or self.min_delta < 0
        ):
            raise ValueError("minimum improvement must be finite and nonnegative")
        if (
            isinstance(self.warmup_trials, bool)
            or not isinstance(self.warmup_trials, int)
            or self.warmup_trials < 1
        ):
            raise ValueError("warmup trials must be a positive integer")

    def should_stop(self, context: StopContext) -> bool:
        if context.completed_trials < self.warmup_trials or not context.objective_scores:
            return False
        best: float | None = None
        since_improvement = 0
        for score in context.objective_scores:
            if score is not None and (best is None or score > best + self.min_delta):
                best = score
                since_improvement = 0
            else:
                since_improvement += 1
        return best is not None and since_improvement >= self.patience

    def fingerprint(self) -> object:
        return {
            "patience": self.patience,
            "min_delta": self.min_delta,
            "warmup_trials": self.warmup_trials,
        }
