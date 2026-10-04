import asyncio
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from tunarag import (
    Candidate,
    InMemoryDataset,
    MetricValue,
    Objective,
    ObjectiveTerm,
    Optimizer,
    Settings,
    SQLiteStore,
    StudyRecord,
    StudyStatus,
    SyncInAsyncContextError,
    TargetScore,
    TrialStatus,
    UsageRecord,
)


class SequenceStrategy:
    def __init__(self, candidates: Sequence[Candidate]) -> None:
        self._candidates = iter(candidates)
        self.observations: list[Candidate] = []

    async def suggest(self) -> Candidate:
        return next(self._candidates)

    async def observe(
        self,
        candidate: Candidate,
        metrics: Sequence[MetricValue],
        usage: Sequence[UsageRecord],
    ) -> None:
        del metrics, usage
        self.observations.append(candidate)


class RepeatingStrategy:
    def __init__(self, candidate: Candidate) -> None:
        self._candidate = candidate

    async def suggest(self) -> Candidate:
        return self._candidate

    async def observe(
        self,
        candidate: Candidate,
        metrics: Sequence[MetricValue],
        usage: Sequence[UsageRecord],
    ) -> None:
        del candidate, metrics, usage


class MultiplyingAdapter:
    async def run(self, candidate: Candidate, example: Any) -> tuple[Any, Sequence[UsageRecord]]:
        multiplier = candidate.parameters["multiplier"]
        if candidate.parameters.get("fail") and example == 2:
            raise RuntimeError("sensitive provider payload")
        return multiplier * example, [UsageRecord("adapter", input_tokens=1, cost=0.1)]


class QualityEvaluator:
    async def evaluate(self, output: Any, example: Any) -> Sequence[MetricValue]:
        del example
        return [MetricValue("quality", float(output))]


class EmptyDataset:
    version = "empty-v1"

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Any]:
        if False:
            yield None


class CapturingStore(SQLiteStore):
    last_study_id: str | None = None

    def create_study(self, name: str, configuration: object) -> StudyRecord:
        study = super().create_study(name, configuration)
        self.last_study_id = study.id
        return study


def settings(tmp_path: Path, *, max_trials: int) -> Settings:
    return Settings.resolve(overrides={"home": tmp_path, "max_trials": max_trials}, environ={})


def test_async_optimizer_executes_trials_and_returns_best_candidate(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "study.sqlite")
    strategy = SequenceStrategy([Candidate({"multiplier": 1}), Candidate({"multiplier": 2})])
    optimizer = Optimizer(
        adapter=MultiplyingAdapter(),
        strategy=strategy,
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=settings(tmp_path, max_trials=2),
    )

    result = asyncio.run(
        optimizer.aoptimize(InMemoryDataset((1, 3), version="numbers-v1"), study_name="quality")
    )

    assert result.study_status is StudyStatus.COMPLETED
    assert result.stop_reason == "MaxTrials"
    assert len(result.successful_trials) == 2
    assert result.best_candidate == Candidate({"multiplier": 2})
    assert result.best_trial is not None
    assert result.best_trial.objective is not None
    assert result.best_trial.objective.score == 4.0
    assert result.usage.input_tokens == 4
    assert result.usage.exact_cost == pytest.approx(0.4)
    assert strategy.observations == [
        Candidate({"multiplier": 1}),
        Candidate({"multiplier": 2}),
    ]
    persisted = store.list_metrics(result.best_trial.id)
    assert [metric.name for metric in persisted] == ["quality", "tunarag.objective"]
    store.close()


def test_trial_failure_is_isolated_and_partial_usage_is_persisted(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "study.sqlite")
    strategy = SequenceStrategy(
        [
            Candidate({"multiplier": 1, "fail": True}),
            Candidate({"multiplier": 2, "fail": False}),
        ]
    )
    optimizer = Optimizer(
        adapter=MultiplyingAdapter(),
        strategy=strategy,
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=settings(tmp_path, max_trials=2),
    )

    result = asyncio.run(
        optimizer.aoptimize(InMemoryDataset((1, 2), version="v1"), study_name="isolation")
    )

    assert [trial.status for trial in result.trials] == [
        TrialStatus.FAILED,
        TrialStatus.SUCCEEDED,
    ]
    assert result.failed_trials[0].error == "adapter failed: RuntimeError"
    assert "sensitive provider payload" not in repr(result)
    assert len(store.list_usage(result.failed_trials[0].id)) == 1
    assert strategy.observations == [Candidate({"multiplier": 2, "fail": False})]
    store.close()


def test_target_score_stops_after_committed_trial(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "target.sqlite")
    strategy = SequenceStrategy([Candidate({"multiplier": 2}), Candidate({"multiplier": 3})])
    optimizer = Optimizer(
        adapter=MultiplyingAdapter(),
        strategy=strategy,
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=Settings.resolve(
            overrides={"home": tmp_path, "max_trials": 2, "concurrency": 1}, environ={}
        ),
        stop_conditions=[TargetScore(2.0)],
    )

    result = asyncio.run(
        optimizer.aoptimize(InMemoryDataset((1,), version="v1"), study_name="target")
    )

    assert result.stop_reason == "TargetScore"
    assert len(result.trials) == 1
    store.close()


def test_duplicate_suggestions_stop_as_search_exhausted(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "study.sqlite")
    candidate = Candidate({"multiplier": 1})
    optimizer = Optimizer(
        adapter=MultiplyingAdapter(),
        strategy=RepeatingStrategy(candidate),
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=settings(tmp_path, max_trials=2),
        duplicate_suggestion_limit=3,
    )

    result = asyncio.run(
        optimizer.aoptimize(InMemoryDataset((1,), version="v1"), study_name="duplicates")
    )

    assert result.stop_reason == "search_exhausted"
    assert len(result.trials) == 1
    event_types = [event.type for event in store.list_events(result.study_id)]
    assert "study.search_exhausted" in event_types
    assert event_types[-2:] == ["study.stopping", "study.completed"]
    store.close()


def test_empty_dataset_finishes_without_a_successful_candidate(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "study.sqlite")
    optimizer = Optimizer(
        adapter=MultiplyingAdapter(),
        strategy=SequenceStrategy([Candidate({"multiplier": 1})]),
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=settings(tmp_path, max_trials=1),
    )

    result = asyncio.run(optimizer.aoptimize(EmptyDataset(), study_name="empty"))

    assert result.best_trial is None
    assert result.trials[0].error == "dataset failed: empty"
    assert result.usage.input_tokens == 0
    store.close()


def test_sync_wrapper_runs_outside_loop_and_rejects_active_loop(tmp_path) -> None:
    first_store = SQLiteStore(tmp_path / "sync.sqlite")
    sync_optimizer = Optimizer(
        adapter=MultiplyingAdapter(),
        strategy=SequenceStrategy([Candidate({"multiplier": 1})]),
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=first_store,
        settings=settings(tmp_path, max_trials=1),
    )
    result = sync_optimizer.optimize(InMemoryDataset((2,), version="v1"), study_name="sync")
    assert result.best_trial is not None
    first_store.close()

    second_store = SQLiteStore(tmp_path / "async.sqlite")
    async_optimizer = Optimizer(
        adapter=MultiplyingAdapter(),
        strategy=SequenceStrategy([Candidate({"multiplier": 1})]),
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=second_store,
        settings=settings(tmp_path, max_trials=1),
    )

    async def call_sync_inside_loop() -> None:
        with pytest.raises(SyncInAsyncContextError):
            async_optimizer.optimize(InMemoryDataset((2,), version="v1"), study_name="invalid")

    asyncio.run(call_sync_inside_loop())
    second_store.close()


def test_cancellation_persists_terminal_states_and_propagates(tmp_path) -> None:
    async def scenario() -> tuple[CapturingStore, str]:
        started = asyncio.Event()

        class BlockingAdapter:
            async def run(
                self, candidate: Candidate, example: Any
            ) -> tuple[Any, Sequence[UsageRecord]]:
                del candidate, example
                started.set()
                await asyncio.Event().wait()
                raise AssertionError("unreachable")

        store = CapturingStore(tmp_path / "cancel.sqlite")
        optimizer = Optimizer(
            adapter=BlockingAdapter(),
            strategy=SequenceStrategy([Candidate({"multiplier": 1})]),
            evaluators=[QualityEvaluator()],
            objective=Objective((ObjectiveTerm("quality"),)),
            store=store,
            settings=settings(tmp_path, max_trials=1),
        )
        task = asyncio.create_task(
            optimizer.aoptimize(InMemoryDataset((1,), version="v1"), study_name="cancel")
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert store.last_study_id is not None
        return store, store.last_study_id

    store, study_id = asyncio.run(scenario())

    assert store.get_study(study_id).status is StudyStatus.CANCELLED
    assert store.list_trials(study_id)[0].status is TrialStatus.CANCELLED
    store.close()
