"""Sequential async optimization engine and synchronous convenience wrapper."""

import asyncio
import sqlite3
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import Any

from .config import Settings
from .contracts import Dataset, Evaluator, RAGAdapter, SearchStrategy
from .domain import Candidate, MetricValue, UsageRecord, ValueStatus
from .errors import SearchSpaceError, SyncInAsyncContextError
from .objective import Objective, ObjectiveResult
from .result import OptimizationResult, TrialSummary, UsageSummary
from .stopping import MaxTrials, StopCondition, StopContext
from .store import SQLiteStore, StudyStatus, TrialRecord, TrialStatus

_OBJECTIVE_METRIC = "tunarag.objective"


@dataclass(slots=True)
class _TrialFailure(Exception):
    stage: str
    cause_type: str
    usage: tuple[UsageRecord, ...]


class Optimizer:
    """Coordinate sequential V0.1 optimization trials through public contracts."""

    def __init__(
        self,
        *,
        adapter: RAGAdapter,
        strategy: SearchStrategy,
        evaluators: Sequence[Evaluator],
        objective: Objective,
        store: SQLiteStore | None = None,
        settings: Settings | None = None,
        stop_conditions: Sequence[StopCondition] | None = None,
        clock: Callable[[], float] = time.monotonic,
        duplicate_suggestion_limit: int = 100,
    ) -> None:
        if not evaluators:
            raise ValueError("optimizer requires at least one evaluator")
        if duplicate_suggestion_limit < 1:
            raise ValueError("duplicate suggestion limit must be positive")
        self._adapter = adapter
        self._strategy = strategy
        self._evaluators = tuple(evaluators)
        self._objective = objective
        self._store = SQLiteStore() if store is None else store
        self._owns_store = store is None
        self._settings = Settings.resolve(environ={}) if settings is None else settings
        self._stop_conditions = (
            (MaxTrials(self._settings.max_trials),)
            if stop_conditions is None
            else tuple(stop_conditions)
        )
        if not self._stop_conditions:
            raise ValueError("optimizer requires at least one stop condition")
        self._clock = clock
        self._duplicate_suggestion_limit = duplicate_suggestion_limit

    @property
    def store(self) -> SQLiteStore:
        """Return the experiment store used by this optimizer."""

        return self._store

    async def aoptimize(self, dataset: Dataset, *, study_name: str) -> OptimizationResult:
        """Run a new study and return terminal results."""

        if not dataset.version.strip():
            raise ValueError("dataset version must not be empty")
        started_at = self._clock()
        study = self._store.create_study(study_name, self._study_configuration(dataset))
        study = self._store.transition_study(study.id, StudyStatus.RUNNING)
        summaries: list[TrialSummary] = []
        stop_reason = "completed"
        try:
            while True:
                stop_reason = self._matching_stop_reason(summaries, started_at)
                if stop_reason:
                    break
                reservation = await self._reserve_next_trial(study.id)
                if reservation is None:
                    stop_reason = "search_exhausted"
                    self._store.append_event(study.id, "study.search_exhausted", {})
                    break
                candidate, trial = reservation
                summary = await self._run_trial(dataset, candidate, trial)
                summaries.append(summary)
                if summary.status is TrialStatus.SUCCEEDED:
                    try:
                        await self._strategy.observe(candidate, summary.metrics, summary.usage)
                    except Exception as error:
                        raise SearchSpaceError(
                            "search strategy failed while observing a committed trial",
                            stage="strategy.observe",
                            details={"cause": type(error).__name__, "trial_id": trial.id},
                        ) from error
            study = self._store.transition_study(study.id, StudyStatus.COMPLETED)
        except asyncio.CancelledError:
            current = self._store.get_study(study.id)
            if current.status is StudyStatus.RUNNING:
                self._store.transition_study(study.id, StudyStatus.CANCELLED)
            raise
        except BaseException:
            current = self._store.get_study(study.id)
            if current.status is StudyStatus.RUNNING:
                self._store.transition_study(study.id, StudyStatus.FAILED)
            raise
        return _build_result(study.id, study.status, stop_reason, summaries)

    def optimize(self, dataset: Dataset, *, study_name: str) -> OptimizationResult:
        """Run `aoptimize` when no event loop is active."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.aoptimize(dataset, study_name=study_name))
        raise SyncInAsyncContextError()

    def close(self) -> None:
        """Close an internally created store; caller-owned stores remain open."""

        if self._owns_store:
            self._store.close()

    async def _reserve_next_trial(self, study_id: str) -> tuple[Candidate, TrialRecord] | None:
        for _ in range(self._duplicate_suggestion_limit):
            try:
                candidate = await self._strategy.suggest()
            except Exception as error:
                raise SearchSpaceError(
                    "search strategy failed while suggesting a candidate",
                    stage="strategy.suggest",
                    details={"cause": type(error).__name__},
                ) from error
            if not isinstance(candidate, Candidate):
                raise SearchSpaceError(
                    "search strategy returned a non-Candidate value",
                    stage="strategy.suggest",
                    details={"type": type(candidate).__name__},
                )
            try:
                return candidate, self._store.reserve_trial(study_id, candidate)
            except sqlite3.IntegrityError as error:
                if "candidate_hash" not in str(error):
                    raise
        return None

    async def _run_trial(
        self, dataset: Dataset, candidate: Candidate, trial: TrialRecord
    ) -> TrialSummary:
        attempt = self._store.start_attempt(trial.id, lease_seconds=86_400.0)
        try:
            metrics, usage = await self._execute_candidate(dataset, candidate)
            try:
                objective = self._objective.evaluate(metrics)
            except Exception as objective_error:
                raise _TrialFailure(
                    "objective", type(objective_error).__name__, usage
                ) from objective_error
            if objective.score is None:
                raise _TrialFailure("objective", "unavailable", usage)
            objective_metric = MetricValue(_OBJECTIVE_METRIC, objective.score, objective.status)
            self._store.commit_trial_result(
                trial.id,
                status=TrialStatus.SUCCEEDED,
                attempt_id=attempt.id,
                metrics=(*metrics, objective_metric),
                usage=usage,
            )
            return TrialSummary(
                id=trial.id,
                sequence=trial.sequence,
                candidate=candidate,
                status=TrialStatus.SUCCEEDED,
                metrics=metrics,
                usage=usage,
                objective=objective,
                attempts=attempt.number + 1,
            )
        except asyncio.CancelledError:
            self._store.commit_trial_result(
                trial.id,
                status=TrialStatus.CANCELLED,
                attempt_id=attempt.id,
                error="trial cancelled",
            )
            raise
        except _TrialFailure as failure:
            failure_message = f"{failure.stage} failed: {failure.cause_type}"
            self._store.commit_trial_result(
                trial.id,
                status=TrialStatus.FAILED,
                attempt_id=attempt.id,
                usage=failure.usage,
                error=failure_message,
            )
            return TrialSummary(
                id=trial.id,
                sequence=trial.sequence,
                candidate=candidate,
                status=TrialStatus.FAILED,
                metrics=(),
                usage=failure.usage,
                objective=None,
                attempts=attempt.number + 1,
                error=failure_message,
            )

    async def _execute_candidate(
        self, dataset: Dataset, candidate: Candidate
    ) -> tuple[tuple[MetricValue, ...], tuple[UsageRecord, ...]]:
        observations: dict[str, list[MetricValue]] = defaultdict(list)
        usage: list[UsageRecord] = []
        sample_count = 0
        stage = "dataset"
        try:
            async for example in dataset:
                sample_count += 1
                stage = "adapter"
                output, sample_usage = await self._adapter.run(candidate, example)
                sample_usage_values = tuple(sample_usage)
                if any(not isinstance(item, UsageRecord) for item in sample_usage_values):
                    raise TypeError("adapter usage must contain UsageRecord values")
                usage.extend(sample_usage_values)
                sample_names: set[str] = set()
                for evaluator in self._evaluators:
                    stage = "evaluation"
                    values = tuple(await evaluator.evaluate(output, example))
                    for metric in values:
                        if not isinstance(metric, MetricValue):
                            raise TypeError("evaluator output must contain MetricValue values")
                        if metric.name == _OBJECTIVE_METRIC:
                            raise ValueError(f"metric name is reserved: {_OBJECTIVE_METRIC}")
                        if metric.name in sample_names:
                            raise ValueError(f"duplicate metric for sample: {metric.name}")
                        sample_names.add(metric.name)
                        observations[metric.name].append(metric)
                stage = "dataset"
        except Exception as error:
            raise _TrialFailure(stage, type(error).__name__, tuple(usage)) from error
        if sample_count == 0:
            raise _TrialFailure("dataset", "empty", tuple(usage))
        if not observations:
            raise _TrialFailure("evaluation", "no_metrics", tuple(usage))
        return _aggregate_metrics(observations, sample_count), tuple(usage)

    def _matching_stop_reason(self, summaries: Sequence[TrialSummary], started_at: float) -> str:
        context = _stop_context(summaries, max(0.0, self._clock() - started_at))
        for condition in self._stop_conditions:
            if condition.should_stop(context):
                return type(condition).__name__
        return ""

    def _study_configuration(self, dataset: Dataset) -> dict[str, Any]:
        return {
            "dataset_version": dataset.version,
            "adapter": _type_name(self._adapter),
            "strategy": _type_name(self._strategy),
            "evaluators": [_type_name(evaluator) for evaluator in self._evaluators],
            "objective": [
                {
                    "metric": term.metric,
                    "weight": term.weight,
                    "direction": term.direction.value,
                    "minimum": term.minimum,
                    "maximum": term.maximum,
                }
                for term in self._objective.terms
            ],
            "max_trials": self._settings.max_trials,
        }


def _aggregate_metrics(
    observations: dict[str, list[MetricValue]], sample_count: int
) -> tuple[MetricValue, ...]:
    aggregated: list[MetricValue] = []
    for name in sorted(observations):
        values = observations[name]
        available = [float(item.value) for item in values if item.value is not None]
        coverage = sum(item.coverage for item in values) / sample_count
        if not available:
            aggregated.append(MetricValue(name, None, ValueStatus.UNAVAILABLE, coverage))
            continue
        status = (
            ValueStatus.ESTIMATED
            if any(item.status is not ValueStatus.EXACT for item in values)
            else ValueStatus.EXACT
        )
        aggregated.append(MetricValue(name, fmean(available), status, coverage))
    return tuple(aggregated)


def _stop_context(summaries: Sequence[TrialSummary], elapsed_seconds: float) -> StopContext:
    exact_cost = 0.0
    estimated_cost = 0.0
    for summary in summaries:
        for item in summary.usage:
            if item.cost is None:
                continue
            if item.status is ValueStatus.EXACT:
                exact_cost += item.cost
            else:
                estimated_cost += item.cost
    return StopContext(len(summaries), exact_cost, estimated_cost, elapsed_seconds)


def _build_result(
    study_id: str,
    study_status: StudyStatus,
    stop_reason: str,
    summaries: Sequence[TrialSummary],
) -> OptimizationResult:
    successful = [
        summary
        for summary in summaries
        if summary.status is TrialStatus.SUCCEEDED
        and summary.objective is not None
        and summary.objective.score is not None
    ]
    best = (
        max(successful, key=lambda item: _objective_score(item.objective)) if successful else None
    )
    all_usage = [item for summary in summaries for item in summary.usage]
    return OptimizationResult(
        study_id=study_id,
        study_status=study_status,
        stop_reason=stop_reason,
        trials=tuple(summaries),
        best_trial=best,
        usage=_usage_summary(all_usage),
    )


def _objective_score(result: ObjectiveResult | None) -> float:
    if result is None or result.score is None:
        raise ValueError("successful trial objective is unavailable")
    return result.score


def _usage_summary(usage: Sequence[UsageRecord]) -> UsageSummary:
    input_tokens = sum(item.input_tokens or 0 for item in usage)
    output_tokens = sum(item.output_tokens or 0 for item in usage)
    exact_cost = sum(item.cost or 0.0 for item in usage if item.status is ValueStatus.EXACT)
    estimated_cost = sum(item.cost or 0.0 for item in usage if item.status is not ValueStatus.EXACT)
    latency = sum(item.latency_seconds or 0.0 for item in usage)
    statuses = {item.status for item in usage}
    if not usage or statuses == {ValueStatus.UNAVAILABLE}:
        status = ValueStatus.UNAVAILABLE
    elif statuses == {ValueStatus.EXACT}:
        status = ValueStatus.EXACT
    else:
        status = ValueStatus.ESTIMATED
    return UsageSummary(
        input_tokens,
        output_tokens,
        exact_cost,
        estimated_cost,
        latency,
        status,
    )


def _type_name(value: object) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"
