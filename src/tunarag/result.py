"""Inspectable optimization result models."""

from dataclasses import dataclass

from .domain import Candidate, MetricValue, UsageRecord, ValueStatus
from .objective import ObjectiveResult
from .store import StudyStatus, TrialStatus


@dataclass(frozen=True, slots=True)
class UsageSummary:
    """Aggregate usage with estimate provenance retained."""

    input_tokens: int
    output_tokens: int
    exact_cost: float
    estimated_cost: float
    latency_seconds: float
    status: ValueStatus


@dataclass(frozen=True, slots=True)
class TrialSummary:
    """Actionable terminal summary for one candidate trial."""

    id: str
    sequence: int
    candidate: Candidate
    status: TrialStatus
    metrics: tuple[MetricValue, ...]
    usage: tuple[UsageRecord, ...]
    objective: ObjectiveResult | None
    attempts: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Completed study result, including failures and no-success outcomes."""

    study_id: str
    study_status: StudyStatus
    stop_reason: str
    trials: tuple[TrialSummary, ...]
    best_trial: TrialSummary | None
    usage: UsageSummary

    @property
    def best_candidate(self) -> Candidate | None:
        """Return the highest-scoring candidate when one succeeded."""

        return None if self.best_trial is None else self.best_trial.candidate

    @property
    def successful_trials(self) -> tuple[TrialSummary, ...]:
        """Return successful trials in execution order."""

        return tuple(trial for trial in self.trials if trial.status is TrialStatus.SUCCEEDED)

    @property
    def failed_trials(self) -> tuple[TrialSummary, ...]:
        """Return failed trials in execution order."""

        return tuple(trial for trial in self.trials if trial.status is TrialStatus.FAILED)
