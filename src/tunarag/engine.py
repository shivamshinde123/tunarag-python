"""Async optimization engine with retries, timeouts, caching, and sync wrapper."""

import asyncio
import json
import sqlite3
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from statistics import fmean
from typing import Any, TypeVar, cast

from .cache import CacheKey, CacheLookupStatus, CachePrivacy
from .config import CachePolicy, Settings
from .contracts import (
    Cache,
    Dataset,
    Evaluator,
    EventCallback,
    Fingerprintable,
    RAGAdapter,
    ReplayableSearchStrategy,
    SearchStrategy,
)
from .domain import Candidate, MetricValue, UsageRecord, ValueStatus
from .errors import ResumeError, SearchSpaceError, SyncInAsyncContextError
from .objective import Objective, ObjectiveResult
from .result import OptimizationResult, TrialSummary, UsageSummary
from .retry import RetryPolicy
from .serialization import content_hash
from .stopping import MaxTrials, StopCondition, StopContext
from .store import AttemptStatus, SQLiteStore, StudyRecord, StudyStatus, TrialRecord, TrialStatus

_OBJECTIVE_METRIC = "tunarag.objective"
_CACHE_PAYLOAD_VERSION = 1
_T = TypeVar("_T")


@dataclass(slots=True)
class _TrialFailure(Exception):
    stage: str
    cause_type: str
    usage: tuple[UsageRecord, ...]
    retryable: bool = False


@dataclass(frozen=True, slots=True)
class _SampleResult:
    metrics: tuple[MetricValue, ...]
    usage: tuple[UsageRecord, ...]


class Optimizer:
    """Coordinate V0.1 optimization trials through public contracts."""

    def __init__(
        self,
        *,
        adapter: RAGAdapter,
        strategy: SearchStrategy,
        evaluators: Sequence[Evaluator],
        objective: Objective,
        store: SQLiteStore | None = None,
        cache: Cache | None = None,
        settings: Settings | None = None,
        stop_conditions: Sequence[StopCondition] | None = None,
        retry_policy: RetryPolicy | None = None,
        callbacks: Sequence[EventCallback] = (),
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
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
        self._cache = cache
        self._settings = Settings.resolve(environ={}) if settings is None else settings
        self._stop_conditions = (
            (MaxTrials(self._settings.max_trials),)
            if stop_conditions is None
            else tuple(stop_conditions)
        )
        if not self._stop_conditions:
            raise ValueError("optimizer requires at least one stop condition")
        self._retry_policy = retry_policy or RetryPolicy(
            max_retries=self._settings.max_retries,
            sample_timeout_seconds=self._settings.sample_timeout_seconds,
            trial_timeout_seconds=self._settings.trial_timeout_seconds,
        )
        self._callbacks = tuple(callbacks)
        self._event_cursors: dict[str, int] = {}
        self._event_locks: dict[str, asyncio.Lock] = {}
        self._sleeper = sleeper
        self._clock = clock
        self._duplicate_suggestion_limit = duplicate_suggestion_limit

    @property
    def store(self) -> SQLiteStore:
        """Return the experiment store used by this optimizer."""

        return self._store

    async def aoptimize(self, dataset: Dataset, *, study_name: str) -> OptimizationResult:
        """Run a new study and return terminal results."""

        self._validate_dataset(dataset)
        study = self._store.create_study(study_name, self._study_configuration(dataset))
        study = self._store.transition_study(study.id, StudyStatus.RUNNING)
        self._event_cursors[study.id] = -1
        self._event_locks[study.id] = asyncio.Lock()
        await self._dispatch_events(study.id)
        return await self._continue_study(dataset, study, [], [])

    async def aresume(self, dataset: Dataset, *, study_id: str) -> OptimizationResult:
        """Resume a compatible durable study after replaying committed successes."""

        self._validate_dataset(dataset)
        try:
            study = self._store.get_study(study_id)
        except KeyError as error:
            raise ResumeError(
                "cannot resume an unknown study",
                stage="resume.load",
                details={"study_id": study_id},
            ) from error
        expected_hash = content_hash(self._study_configuration(dataset), namespace="study:v1")
        if study.config_hash != expected_hash:
            raise ResumeError(
                "study configuration is incompatible with the current optimizer",
                stage="resume.validate",
                details={"study_id": study_id},
            )
        if study.status in {StudyStatus.FAILED, StudyStatus.CANCELLED}:
            raise ResumeError(
                "failed or cancelled studies are terminal and cannot resume",
                stage="resume.validate",
                details={"study_id": study_id, "status": study.status.value},
            )

        self._event_cursors[study.id] = self._latest_event_sequence(study.id)
        self._event_locks[study.id] = asyncio.Lock()
        summaries = self._load_terminal_summaries(study.id)
        if study.status is StudyStatus.COMPLETED:
            await self._replay_strategy(study.id, summaries)
            return _build_result(
                study.id, study.status, self._persisted_stop_reason(study.id), summaries
            )
        if study.status is StudyStatus.CREATED:
            study = self._store.transition_study(study.id, StudyStatus.RUNNING)

        abandoned = self._store.abandon_expired_attempts(study_id=study.id)
        recoverable_ids = {trial.id for trial in self._store.list_recoverable_trials(study.id)}
        unfinished = [
            trial
            for trial in self._store.list_trials(study.id)
            if trial.status is TrialStatus.PENDING or trial.id in recoverable_ids
        ]
        active = [
            trial.id
            for trial in self._store.list_trials(study.id)
            if trial.status is TrialStatus.RUNNING and trial.id not in recoverable_ids
        ]
        if active:
            await self._dispatch_events(study.id)
            raise ResumeError(
                "study has attempts with active recovery leases",
                stage="resume.recover",
                retryable=True,
                details={"study_id": study.id, "trial_ids": active},
            )
        await self._replay_strategy(study.id, summaries)
        self._store.append_event(
            study.id,
            "study.resumed",
            {
                "terminal_trials": len(summaries),
                "unfinished_trials": len(unfinished),
                "abandoned_attempts": len(abandoned),
            },
        )
        await self._dispatch_events(study.id)
        return await self._continue_study(dataset, study, summaries, unfinished)

    async def _continue_study(
        self,
        dataset: Dataset,
        study: StudyRecord,
        summaries: list[TrialSummary],
        unfinished: Sequence[TrialRecord],
    ) -> OptimizationResult:
        started_at = self._clock()
        pending = list(unfinished)
        stop_reason = "completed"
        search_exhausted = False
        try:
            while True:
                recovering = bool(pending)
                capacity = (
                    self._settings.concurrency if recovering else self._batch_capacity(summaries)
                )
                if capacity == 0:
                    stop_reason = self._matching_stop_reason(summaries, started_at)
                    break
                batch: list[tuple[Candidate, TrialRecord]] = []
                while pending and len(batch) < capacity:
                    trial = pending.pop(0)
                    batch.append((_candidate_from_trial(trial), trial))
                while not recovering and len(batch) < capacity and not search_exhausted:
                    stop_reason = self._matching_stop_reason(summaries, started_at)
                    if stop_reason:
                        break
                    reservation = await self._reserve_next_trial(study.id)
                    if reservation is None:
                        search_exhausted = True
                        self._store.append_event(study.id, "study.search_exhausted", {})
                        break
                    batch.append(reservation)
                    await self._dispatch_events(study.id)
                if not batch:
                    if search_exhausted:
                        stop_reason = "search_exhausted"
                    break
                completed = await asyncio.gather(
                    *(self._run_trial(dataset, candidate, trial) for candidate, trial in batch)
                )
                for summary in sorted(completed, key=lambda item: item.sequence):
                    summaries.append(summary)
                    if summary.status is TrialStatus.SUCCEEDED:
                        await self._observe_success(summary)
            self._store.append_event(study.id, "study.stopping", {"reason": stop_reason})
            study = self._store.transition_study(study.id, StudyStatus.COMPLETED)
            await self._dispatch_events(study.id)
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

    def resume(self, dataset: Dataset, *, study_id: str) -> OptimizationResult:
        """Run `aresume` when no event loop is active."""

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.aresume(dataset, study_id=study_id))
        raise SyncInAsyncContextError()

    def close(self) -> None:
        """Close an internally created store; caller-owned resources remain open."""

        if self._owns_store:
            self._store.close()

    def _latest_event_sequence(self, study_id: str) -> int:
        events = self._store.list_events(study_id)
        return -1 if not events else events[-1].sequence

    async def _dispatch_events(self, study_id: str) -> None:
        lock = self._event_locks.setdefault(study_id, asyncio.Lock())
        async with lock:
            cursor = self._event_cursors.get(study_id, -1)
            events = self._store.list_events(study_id, after_sequence=cursor)
            for event in events:
                self._event_cursors[study_id] = event.sequence
                if event.type == "callback.failed":
                    continue
                for index, callback in enumerate(self._callbacks):
                    try:
                        await callback.on_event(event)
                    except Exception as error:
                        self._store.append_event(
                            study_id,
                            "callback.failed",
                            {
                                "source_sequence": event.sequence,
                                "callback_index": index,
                                "callback": _type_name(callback),
                                "cause": type(error).__name__,
                            },
                        )
            self._event_cursors[study_id] = self._latest_event_sequence(study_id)

    def _batch_capacity(self, summaries: Sequence[TrialSummary]) -> int:
        capacity = self._settings.concurrency
        for condition in self._stop_conditions:
            if isinstance(condition, MaxTrials):
                capacity = min(capacity, max(0, condition.limit - len(summaries)))
        return capacity

    @staticmethod
    def _validate_dataset(dataset: Dataset) -> None:
        if not dataset.version.strip():
            raise ValueError("dataset version must not be empty")

    def _load_terminal_summaries(self, study_id: str) -> list[TrialSummary]:
        cached_trial_ids = {
            event.payload.get("trial_id")
            for event in self._store.list_events(study_id)
            if event.type == "trial.cache_hit"
        }
        summaries: list[TrialSummary] = []
        for trial in self._store.list_trials(study_id):
            if trial.status in {TrialStatus.PENDING, TrialStatus.RUNNING}:
                continue
            persisted_metrics = self._store.list_metrics(trial.id)
            objective_values = [
                metric for metric in persisted_metrics if metric.name == _OBJECTIVE_METRIC
            ]
            metrics = tuple(
                metric for metric in persisted_metrics if metric.name != _OBJECTIVE_METRIC
            )
            objective: ObjectiveResult | None = None
            if trial.status is TrialStatus.SUCCEEDED:
                if len(objective_values) != 1 or objective_values[0].value is None:
                    raise ResumeError(
                        "successful trial is missing its committed objective",
                        stage="resume.replay",
                        details={"study_id": study_id, "trial_id": trial.id},
                    )
                objective = ObjectiveResult(objective_values[0].value, objective_values[0].status)
            usage = tuple(item.usage for item in self._store.list_usage(trial.id))
            summaries.append(
                TrialSummary(
                    id=trial.id,
                    sequence=trial.sequence,
                    candidate=_candidate_from_trial(trial),
                    status=trial.status,
                    metrics=metrics,
                    usage=usage,
                    objective=objective,
                    attempts=len(self._store.list_attempts(trial.id)),
                    cached=trial.id in cached_trial_ids,
                    error=trial.error,
                )
            )
        return summaries

    async def _replay_strategy(self, study_id: str, summaries: Sequence[TrialSummary]) -> None:
        by_id = {summary.id: summary for summary in summaries}
        current_trial_id: str | None = None
        try:
            for trial in self._store.list_trials(study_id):
                current_trial_id = trial.id
                summary = by_id.get(trial.id)
                if isinstance(self._strategy, ReplayableSearchStrategy):
                    await self._strategy.replay(
                        _candidate_from_trial(trial),
                        () if summary is None else summary.metrics,
                        () if summary is None else summary.usage,
                    )
                elif summary is not None and summary.status is TrialStatus.SUCCEEDED:
                    await self._strategy.observe(summary.candidate, summary.metrics, summary.usage)
        except Exception as error:
            raise ResumeError(
                "search strategy failed while replaying reserved trials",
                stage="resume.replay",
                details={"cause": type(error).__name__, "trial_id": current_trial_id},
            ) from error

    async def _observe_success(self, summary: TrialSummary) -> None:
        try:
            await self._strategy.observe(summary.candidate, summary.metrics, summary.usage)
        except Exception as error:
            raise SearchSpaceError(
                "search strategy failed while observing a committed trial",
                stage="strategy.observe",
                details={"cause": type(error).__name__, "trial_id": summary.id},
            ) from error

    def _persisted_stop_reason(self, study_id: str) -> str:
        reasons = [
            event.payload.get("reason")
            for event in self._store.list_events(study_id)
            if event.type == "study.stopping"
        ]
        return reasons[-1] if reasons and isinstance(reasons[-1], str) else "already_completed"

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
        cache_key = self._cache_key(dataset, candidate)
        cached_metrics = self._read_cache(trial, cache_key)
        accumulated_usage: list[UsageRecord] = []
        while True:
            attempt = self._store.start_attempt(
                trial.id, lease_seconds=self._retry_policy.lease_seconds
            )
            await self._dispatch_events(trial.study_id)
            try:
                if cached_metrics is None:
                    metrics, usage = await _wait_for(
                        self._execute_candidate(dataset, candidate),
                        self._retry_policy.trial_timeout_seconds,
                    )
                else:
                    metrics, usage = cached_metrics, ()
                objective = self._evaluate_objective(metrics, usage)
                accumulated_usage.extend(usage)
                objective_metric = MetricValue(
                    _OBJECTIVE_METRIC, cast(float, objective.score), objective.status
                )
                self._store.commit_trial_result(
                    trial.id,
                    status=TrialStatus.SUCCEEDED,
                    attempt_id=attempt.id,
                    metrics=(*metrics, objective_metric),
                    usage=usage,
                )
                cached = cached_metrics is not None
                if cached:
                    self._store.append_event(
                        trial.study_id, "trial.cache_hit", {"trial_id": trial.id}
                    )
                else:
                    self._write_cache(trial, cache_key, metrics)
                await self._dispatch_events(trial.study_id)
                return TrialSummary(
                    id=trial.id,
                    sequence=trial.sequence,
                    candidate=candidate,
                    status=TrialStatus.SUCCEEDED,
                    metrics=metrics,
                    usage=tuple(accumulated_usage),
                    objective=objective,
                    attempts=attempt.number + 1,
                    cached=cached,
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
                accumulated_usage.extend(failure.usage)
                failure_message = f"{failure.stage} failed: {failure.cause_type}"
                if failure.retryable and attempt.number < self._retry_policy.max_retries:
                    self._store.finish_attempt(
                        attempt.id,
                        AttemptStatus.FAILED,
                        usage=failure.usage,
                        error=failure_message,
                    )
                    delay = self._retry_policy.delay_before_retry(attempt.number)
                    self._store.append_event(
                        trial.study_id,
                        "trial.retry_scheduled",
                        {
                            "trial_id": trial.id,
                            "attempt": attempt.number,
                            "delay_seconds": delay,
                        },
                    )
                    await self._dispatch_events(trial.study_id)
                    try:
                        await self._sleeper(delay)
                    except asyncio.CancelledError:
                        self._store.transition_trial(trial.id, TrialStatus.CANCELLED)
                        raise
                    cached_metrics = None
                    continue
                self._store.commit_trial_result(
                    trial.id,
                    status=TrialStatus.FAILED,
                    attempt_id=attempt.id,
                    usage=failure.usage,
                    error=failure_message,
                )
                await self._dispatch_events(trial.study_id)
                return TrialSummary(
                    id=trial.id,
                    sequence=trial.sequence,
                    candidate=candidate,
                    status=TrialStatus.FAILED,
                    metrics=(),
                    usage=tuple(accumulated_usage),
                    objective=None,
                    attempts=attempt.number + 1,
                    cached=cached_metrics is not None,
                    error=failure_message,
                )
            except Exception as error:
                classified_failure = _TrialFailure(
                    "trial", type(error).__name__, (), self._retry_policy.is_retryable(error)
                )
                accumulated_usage.extend(classified_failure.usage)
                failure_message = (
                    f"{classified_failure.stage} failed: {classified_failure.cause_type}"
                )
                if classified_failure.retryable and attempt.number < self._retry_policy.max_retries:
                    self._store.finish_attempt(
                        attempt.id, AttemptStatus.FAILED, error=failure_message
                    )
                    delay = self._retry_policy.delay_before_retry(attempt.number)
                    self._store.append_event(
                        trial.study_id,
                        "trial.retry_scheduled",
                        {
                            "trial_id": trial.id,
                            "attempt": attempt.number,
                            "delay_seconds": delay,
                        },
                    )
                    await self._dispatch_events(trial.study_id)
                    try:
                        await self._sleeper(delay)
                    except asyncio.CancelledError:
                        self._store.transition_trial(trial.id, TrialStatus.CANCELLED)
                        raise
                    cached_metrics = None
                    continue
                self._store.commit_trial_result(
                    trial.id,
                    status=TrialStatus.FAILED,
                    attempt_id=attempt.id,
                    error=failure_message,
                )
                await self._dispatch_events(trial.study_id)
                return TrialSummary(
                    id=trial.id,
                    sequence=trial.sequence,
                    candidate=candidate,
                    status=TrialStatus.FAILED,
                    metrics=(),
                    usage=tuple(accumulated_usage),
                    objective=None,
                    attempts=attempt.number + 1,
                    cached=False,
                    error=failure_message,
                )

    async def _execute_candidate(
        self, dataset: Dataset, candidate: Candidate
    ) -> tuple[tuple[MetricValue, ...], tuple[UsageRecord, ...]]:
        observations: dict[str, list[MetricValue]] = defaultdict(list)
        usage: list[UsageRecord] = []
        try:
            examples = [example async for example in dataset]
        except Exception as error:
            raise _TrialFailure(
                "dataset",
                type(error).__name__,
                (),
                self._retry_policy.is_retryable(error),
            ) from error
        if not examples:
            raise _TrialFailure("dataset", "empty", tuple(usage))

        semaphore = asyncio.Semaphore(self._settings.sample_concurrency)

        async def bounded(example: Any) -> _SampleResult:
            async with semaphore:
                return await self._execute_sample(candidate, example)

        outcomes = await asyncio.gather(
            *(bounded(example) for example in examples), return_exceptions=True
        )
        first_failure: _TrialFailure | None = None
        for outcome in outcomes:
            if isinstance(outcome, _TrialFailure):
                usage.extend(outcome.usage)
                if first_failure is None:
                    first_failure = outcome
                continue
            if isinstance(outcome, BaseException):
                raise outcome
            usage.extend(outcome.usage)
            for metric in outcome.metrics:
                observations[metric.name].append(metric)
        if first_failure is not None:
            raise _TrialFailure(
                first_failure.stage,
                first_failure.cause_type,
                tuple(usage),
                first_failure.retryable,
            ) from first_failure
        if not observations:
            raise _TrialFailure("evaluation", "no_metrics", tuple(usage))
        return _aggregate_metrics(observations, len(examples)), tuple(usage)

    async def _execute_sample(self, candidate: Candidate, example: Any) -> _SampleResult:
        usage: tuple[UsageRecord, ...] = ()
        stage = "adapter"
        try:
            output, sample_usage = await _wait_for(
                self._adapter.run(candidate, example),
                self._retry_policy.sample_timeout_seconds,
            )
            usage = tuple(sample_usage)
            if any(not isinstance(item, UsageRecord) for item in usage):
                raise TypeError("adapter usage must contain UsageRecord values")
            sample_metrics: list[MetricValue] = []
            sample_names: set[str] = set()
            for evaluator in self._evaluators:
                stage = "evaluation"
                values = tuple(
                    await _wait_for(
                        evaluator.evaluate(output, example),
                        self._retry_policy.sample_timeout_seconds,
                    )
                )
                for metric in values:
                    if not isinstance(metric, MetricValue):
                        raise TypeError("evaluator output must contain MetricValue values")
                    if metric.name == _OBJECTIVE_METRIC:
                        raise ValueError(f"metric name is reserved: {_OBJECTIVE_METRIC}")
                    if metric.name in sample_names:
                        raise ValueError(f"duplicate metric for sample: {metric.name}")
                    sample_names.add(metric.name)
                    sample_metrics.append(metric)
            return _SampleResult(tuple(sample_metrics), usage)
        except Exception as error:
            raise _TrialFailure(
                stage,
                type(error).__name__,
                usage,
                self._retry_policy.is_retryable(error),
            ) from error

    def _evaluate_objective(
        self, metrics: Sequence[MetricValue], usage: tuple[UsageRecord, ...]
    ) -> ObjectiveResult:
        try:
            objective = self._objective.evaluate(metrics)
        except Exception as error:
            raise _TrialFailure(
                "objective",
                type(error).__name__,
                usage,
                self._retry_policy.is_retryable(error),
            ) from error
        if objective.score is None:
            raise _TrialFailure("objective", "unavailable", usage)
        return objective

    def _read_cache(self, trial: TrialRecord, key: CacheKey) -> tuple[MetricValue, ...] | None:
        if self._cache is None or self._settings.cache_policy not in {
            CachePolicy.READ_ONLY,
            CachePolicy.READ_WRITE,
        }:
            return None
        try:
            lookup = self._cache.get(key)
        except Exception as error:
            self._store.append_event(
                trial.study_id,
                "trial.cache_read_failed",
                {"trial_id": trial.id, "cause": type(error).__name__},
            )
            return None
        if lookup.status is not CacheLookupStatus.HIT or lookup.payload is None:
            return None
        try:
            return _decode_cached_metrics(lookup.payload)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            self._store.append_event(
                trial.study_id,
                "trial.cache_decode_failed",
                {"trial_id": trial.id, "cause": type(error).__name__},
            )
            return None

    def _write_cache(
        self, trial: TrialRecord, key: CacheKey, metrics: Sequence[MetricValue]
    ) -> None:
        if self._cache is None or self._settings.cache_policy not in {
            CachePolicy.WRITE_ONLY,
            CachePolicy.READ_WRITE,
        }:
            return
        try:
            self._cache.put(
                key,
                _encode_cached_metrics(metrics),
                privacy=CachePrivacy.SENSITIVE,
            )
        except Exception as error:
            self._store.append_event(
                trial.study_id,
                "trial.cache_write_failed",
                {"trial_id": trial.id, "cause": type(error).__name__},
            )

    def _cache_key(self, dataset: Dataset, candidate: Candidate) -> CacheKey:
        return CacheKey.from_parts(
            "evaluation",
            {
                "payload_version": _CACHE_PAYLOAD_VERSION,
                "dataset_version": dataset.version,
                "candidate": candidate.parameters,
                "adapter": _component_identity(self._adapter),
                "evaluators": [_component_identity(item) for item in self._evaluators],
            },
            format_version=_CACHE_PAYLOAD_VERSION,
        )

    def _matching_stop_reason(self, summaries: Sequence[TrialSummary], started_at: float) -> str:
        context = _stop_context(summaries, max(0.0, self._clock() - started_at))
        for condition in self._stop_conditions:
            if condition.should_stop(context):
                return type(condition).__name__
        return ""

    def _study_configuration(self, dataset: Dataset) -> dict[str, Any]:
        return {
            "dataset_version": dataset.version,
            "adapter": _component_identity(self._adapter),
            "strategy": _component_identity(self._strategy),
            "evaluators": [_component_identity(item) for item in self._evaluators],
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
            "max_retries": self._retry_policy.max_retries,
            "sample_timeout_seconds": self._retry_policy.sample_timeout_seconds,
            "trial_timeout_seconds": self._retry_policy.trial_timeout_seconds,
            "cache_policy": self._settings.cache_policy.value,
        }


async def _wait_for(awaitable: Awaitable[_T], timeout: float | None) -> _T:
    if timeout is None:
        return await awaitable
    return await asyncio.wait_for(awaitable, timeout)


def _encode_cached_metrics(metrics: Sequence[MetricValue]) -> bytes:
    document = {
        "version": _CACHE_PAYLOAD_VERSION,
        "metrics": [
            {
                "name": metric.name,
                "value": metric.value,
                "status": metric.status.value,
                "coverage": metric.coverage,
            }
            for metric in metrics
        ],
    }
    return json.dumps(document, ensure_ascii=True, separators=(",", ":"), sort_keys=True).encode()


def _decode_cached_metrics(payload: bytes) -> tuple[MetricValue, ...]:
    document = json.loads(payload.decode("utf-8"))
    if not isinstance(document, dict) or document.get("version") != _CACHE_PAYLOAD_VERSION:
        raise ValueError("unsupported cached evaluation payload")
    items = document.get("metrics")
    if not isinstance(items, list) or not items:
        raise ValueError("cached evaluation metrics must be a nonempty list")
    metrics: list[MetricValue] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise TypeError("cached metric must be an object")
        metrics.append(
            MetricValue(
                name=_required_string(item, "name"),
                value=_optional_number(item.get("value")),
                status=ValueStatus(_required_string(item, "status")),
                coverage=_required_number(item, "coverage"),
            )
        )
    if len({metric.name for metric in metrics}) != len(metrics):
        raise ValueError("cached evaluation contains duplicate metric names")
    return tuple(metrics)


def _required_string(item: Mapping[str, Any], key: str) -> str:
    value = item.get(key)
    if not isinstance(value, str):
        raise TypeError(f"cached metric {key} must be a string")
    return value


def _required_number(item: Mapping[str, Any], key: str) -> float:
    value = item.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"cached metric {key} must be numeric")
    return float(value)


def _optional_number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("cached metric value must be numeric or null")
    return float(value)


def _candidate_from_trial(trial: TrialRecord) -> Candidate:
    parameters = json.loads(trial.candidate_json)
    if not isinstance(parameters, Mapping):
        raise ResumeError(
            "persisted candidate is not an object",
            stage="resume.replay",
            details={"trial_id": trial.id},
        )
    try:
        return Candidate(dict(parameters))
    except (TypeError, ValueError) as error:
        raise ResumeError(
            "persisted candidate is invalid",
            stage="resume.replay",
            details={"trial_id": trial.id, "cause": type(error).__name__},
        ) from error


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


def _component_identity(value: object) -> dict[str, Any]:
    identity: dict[str, Any] = {"type": _type_name(value)}
    if isinstance(value, Fingerprintable):
        identity["fingerprint"] = value.fingerprint()
    return identity
