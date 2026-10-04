"""Inspectable optimization result models."""

import csv
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from .domain import Candidate, MetricValue, UsageRecord, ValueStatus
from .errors import redact
from .objective import ObjectiveDirection, ObjectiveResult
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
    cached: bool = False
    error: str | None = None

    def metric(self, name: str) -> MetricValue | None:
        """Return one named metric, or None when it was not observed."""

        return next((metric for metric in self.metrics if metric.name == name), None)


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

    @property
    def ranked_trials(self) -> tuple[TrialSummary, ...]:
        """Return successful trials by descending objective, then sequence."""

        return tuple(
            sorted(
                (
                    trial
                    for trial in self.successful_trials
                    if trial.objective is not None and trial.objective.score is not None
                ),
                key=lambda trial: (-_objective_score(trial), trial.sequence),
            )
        )

    @property
    def metric_names(self) -> tuple[str, ...]:
        """Return all observed metric names in lexical order."""

        return tuple(sorted({metric.name for trial in self.trials for metric in trial.metrics}))

    def metric_leaders(
        self,
        name: str,
        *,
        direction: ObjectiveDirection = ObjectiveDirection.MAXIMIZE,
    ) -> tuple[TrialSummary, ...]:
        """Rank successful trials that have an available named metric."""

        if not name.strip():
            raise ValueError("metric name must not be empty")
        trials = [
            trial
            for trial in self.successful_trials
            if (metric := trial.metric(name)) is not None and metric.value is not None
        ]
        multiplier = -1.0 if direction is ObjectiveDirection.MAXIMIZE else 1.0
        return tuple(
            sorted(
                trials,
                key=lambda trial: (
                    multiplier * cast(float, cast(MetricValue, trial.metric(name)).value),
                    trial.sequence,
                ),
            )
        )

    def as_dict(self) -> dict[str, Any]:
        """Return a redacted, JSON-compatible report."""

        return {
            "schema_version": 1,
            "study_id": self.study_id,
            "study_status": self.study_status.value,
            "stop_reason": self.stop_reason,
            "best_trial_id": None if self.best_trial is None else self.best_trial.id,
            "counts": {
                "trials": len(self.trials),
                "successful": len(self.successful_trials),
                "failed": len(self.failed_trials),
            },
            "usage": _usage_dict(self.usage),
            "trials": [_trial_dict(trial) for trial in self.trials],
        }

    def to_json(self, *, indent: int | None = 2) -> str:
        """Serialize the redacted report to deterministic JSON."""

        return json.dumps(
            self.as_dict(),
            ensure_ascii=False,
            allow_nan=False,
            indent=indent,
            sort_keys=True,
        )

    def write_json(self, path: str | Path, *, indent: int | None = 2) -> Path:
        """Write a redacted JSON report and return its path."""

        target = Path(path)
        target.write_text(self.to_json(indent=indent) + "\n", encoding="utf-8")
        return target

    def write_csv(self, path: str | Path) -> Path:
        """Write one redacted, flattened row per trial and return its path."""

        target = Path(path)
        metric_columns = [
            column
            for name in self.metric_names
            for column in (
                f"metric.{name}.value",
                f"metric.{name}.status",
                f"metric.{name}.coverage",
            )
        ]
        fieldnames = [
            "study_id",
            "trial_id",
            "sequence",
            "status",
            "objective_score",
            "objective_status",
            "attempts",
            "cached",
            "error",
            "candidate",
            "input_tokens",
            "output_tokens",
            "exact_cost",
            "estimated_cost",
            "latency_seconds",
            "usage_status",
            *metric_columns,
        ]
        with target.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="raise")
            writer.writeheader()
            for trial in self.trials:
                writer.writerow(_trial_csv_row(self.study_id, trial, self.metric_names))
        return target


def _usage_dict(usage: UsageSummary) -> dict[str, Any]:
    return {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "exact_cost": usage.exact_cost,
        "estimated_cost": usage.estimated_cost,
        "latency_seconds": usage.latency_seconds,
        "status": usage.status.value,
    }


def _trial_dict(trial: TrialSummary) -> dict[str, Any]:
    candidate = cast(Mapping[str, Any], redact(trial.candidate.parameters))
    return {
        "id": trial.id,
        "sequence": trial.sequence,
        "status": trial.status.value,
        "candidate": dict(candidate),
        "metrics": [
            {
                "name": metric.name,
                "value": metric.value,
                "status": metric.status.value,
                "coverage": metric.coverage,
            }
            for metric in trial.metrics
        ],
        "usage": [
            {
                "component": item.component,
                "input_tokens": item.input_tokens,
                "output_tokens": item.output_tokens,
                "cost": item.cost,
                "latency_seconds": item.latency_seconds,
                "status": item.status.value,
                "pricing_version": item.pricing_version,
            }
            for item in trial.usage
        ],
        "objective": (
            None
            if trial.objective is None
            else {"score": trial.objective.score, "status": trial.objective.status.value}
        ),
        "attempts": trial.attempts,
        "cached": trial.cached,
        "error": trial.error,
    }


def _trial_csv_row(
    study_id: str, trial: TrialSummary, metric_names: tuple[str, ...]
) -> dict[str, Any]:
    usage = _summarize_usage(trial.usage)
    candidate = redact(trial.candidate.parameters)
    row: dict[str, Any] = {
        "study_id": study_id,
        "trial_id": trial.id,
        "sequence": trial.sequence,
        "status": trial.status.value,
        "objective_score": None if trial.objective is None else trial.objective.score,
        "objective_status": None if trial.objective is None else trial.objective.status.value,
        "attempts": trial.attempts,
        "cached": trial.cached,
        "error": trial.error,
        "candidate": json.dumps(
            candidate, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "exact_cost": usage.exact_cost,
        "estimated_cost": usage.estimated_cost,
        "latency_seconds": usage.latency_seconds,
        "usage_status": usage.status.value,
    }
    for name in metric_names:
        metric = trial.metric(name)
        row[f"metric.{name}.value"] = None if metric is None else metric.value
        row[f"metric.{name}.status"] = None if metric is None else metric.status.value
        row[f"metric.{name}.coverage"] = None if metric is None else metric.coverage
    return row


def _objective_score(trial: TrialSummary) -> float:
    if trial.objective is None or trial.objective.score is None:
        raise ValueError("ranked trial has no objective score")
    return trial.objective.score


def _summarize_usage(records: tuple[UsageRecord, ...]) -> UsageSummary:
    statuses = {record.status for record in records}
    if not records or statuses == {ValueStatus.UNAVAILABLE}:
        status = ValueStatus.UNAVAILABLE
    elif statuses == {ValueStatus.EXACT}:
        status = ValueStatus.EXACT
    else:
        status = ValueStatus.ESTIMATED
    return UsageSummary(
        input_tokens=sum(record.input_tokens or 0 for record in records),
        output_tokens=sum(record.output_tokens or 0 for record in records),
        exact_cost=sum(
            record.cost or 0.0 for record in records if record.status is ValueStatus.EXACT
        ),
        estimated_cost=sum(
            record.cost or 0.0 for record in records if record.status is not ValueStatus.EXACT
        ),
        latency_seconds=sum(record.latency_seconds or 0.0 for record in records),
        status=status,
    )
