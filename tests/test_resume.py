import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from pipeline_fixtures import framework_fixture

from tunarag import (
    AttemptStatus,
    CachePolicy,
    Candidate,
    InMemoryDataset,
    MetricValue,
    Objective,
    ObjectiveTerm,
    Optimizer,
    ResumeError,
    RetryPolicy,
    Settings,
    SQLiteStore,
    StudyStatus,
    TrialStatus,
    UsageRecord,
)
from tunarag.search import IntegerRange, RandomSearch, SearchSpace


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


class ReplayTrackingStrategy(SequenceStrategy):
    def __init__(self, candidates: Sequence[Candidate]) -> None:
        super().__init__(candidates)
        self.replayed: list[Candidate] = []

    async def replay(
        self,
        candidate: Candidate,
        metrics: Sequence[MetricValue],
        usage: Sequence[UsageRecord],
    ) -> None:
        del metrics, usage
        self.replayed.append(candidate)


class MultiplyingAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, candidate: Candidate, example: Any) -> tuple[Any, Sequence[UsageRecord]]:
        self.calls += 1
        return candidate.parameters["multiplier"] * example, [
            UsageRecord("adapter", input_tokens=1, cost=0.1)
        ]


class QualityEvaluator:
    async def evaluate(self, output: Any, example: Any) -> Sequence[MetricValue]:
        del example
        return [MetricValue("quality", float(output))]


def settings(tmp_path: Path, *, max_trials: int) -> Settings:
    return Settings.resolve(
        overrides={
            "home": tmp_path,
            "max_trials": max_trials,
            "cache_policy": CachePolicy.OFF,
        },
        environ={},
    )


def optimizer_for(
    store: SQLiteStore,
    tmp_path: Path,
    strategy: SequenceStrategy,
    *,
    max_trials: int,
    adapter: MultiplyingAdapter | None = None,
) -> Optimizer:
    return Optimizer(
        adapter=framework_fixture(adapter or MultiplyingAdapter()),
        strategy=strategy,
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=settings(tmp_path, max_trials=max_trials),
        retry_policy=RetryPolicy(max_retries=0),
    )


def seed_interrupted_study(store: SQLiteStore, tmp_path: Path) -> tuple[str, str, InMemoryDataset]:
    dataset = InMemoryDataset((2,), version="numbers-v1")
    optimizer = optimizer_for(store, tmp_path, SequenceStrategy(()), max_trials=2)
    study = store.create_study("resume", optimizer._study_configuration(dataset))
    store.transition_study(study.id, StudyStatus.RUNNING)

    first = store.reserve_trial(study.id, Candidate({"multiplier": 1.0}))
    first_attempt = store.start_attempt(first.id, lease_seconds=1.0, now=0.0)
    store.commit_trial_result(
        first.id,
        status=TrialStatus.SUCCEEDED,
        attempt_id=first_attempt.id,
        metrics=(MetricValue("quality", 2.0), MetricValue("tunarag.objective", 2.0)),
        usage=(UsageRecord("adapter", input_tokens=1, cost=0.1),),
        now=0.5,
    )

    second = store.reserve_trial(study.id, Candidate({"multiplier": 1.5}))
    store.start_attempt(second.id, lease_seconds=1.0, now=0.0)
    return study.id, second.id, dataset


def test_resume_replays_success_and_recovers_expired_attempt(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "resume.sqlite", clock=lambda: 10.0)
    study_id, recovered_trial_id, dataset = seed_interrupted_study(store, tmp_path)
    strategy = SequenceStrategy(())
    adapter = MultiplyingAdapter()
    optimizer = optimizer_for(store, tmp_path, strategy, max_trials=2, adapter=adapter)

    result = asyncio.run(optimizer.aresume(dataset, study_id=study_id))

    assert result.study_status is StudyStatus.COMPLETED
    assert result.stop_reason == "MaxTrials"
    assert [trial.sequence for trial in result.trials] == [0, 1]
    assert result.trials[1].candidate.parameters["multiplier"] == 1.5
    assert result.trials[1].objective is not None
    assert result.trials[1].objective.score == 3.0
    assert result.usage.input_tokens == 2
    assert adapter.calls == 1
    assert strategy.observations == [
        Candidate({"multiplier": 1.0}),
        Candidate({"multiplier": 1.5}),
    ]
    assert [attempt.status for attempt in store.list_attempts(recovered_trial_id)] == [
        AttemptStatus.ABANDONED,
        AttemptStatus.SUCCEEDED,
    ]
    assert any(event.type == "study.resumed" for event in store.list_events(study_id))
    store.close()


def test_resume_rejects_incompatible_configuration_without_mutating_study(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "incompatible.sqlite")
    original_dataset = InMemoryDataset((1,), version="v1")
    optimizer = optimizer_for(store, tmp_path, SequenceStrategy(()), max_trials=1)
    study = store.create_study("incompatible", optimizer._study_configuration(original_dataset))
    store.transition_study(study.id, StudyStatus.RUNNING)

    with pytest.raises(ResumeError, match="incompatible"):
        asyncio.run(optimizer.aresume(InMemoryDataset((1,), version="v2"), study_id=study.id))

    assert store.get_study(study.id).status is StudyStatus.RUNNING
    store.close()


def test_resume_rejects_an_attempt_with_an_active_lease(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "active.sqlite", clock=lambda: 10.0)
    dataset = InMemoryDataset((1,), version="v1")
    strategy = SequenceStrategy(())
    optimizer = optimizer_for(store, tmp_path, strategy, max_trials=1)
    study = store.create_study("active", optimizer._study_configuration(dataset))
    store.transition_study(study.id, StudyStatus.RUNNING)
    trial = store.reserve_trial(study.id, Candidate({"multiplier": 1}))
    store.start_attempt(trial.id, lease_seconds=10.0, now=10.0)

    with pytest.raises(ResumeError, match="active recovery leases") as captured:
        asyncio.run(optimizer.aresume(dataset, study_id=study.id))

    assert captured.value.retryable
    assert strategy.observations == []
    assert store.list_attempts(trial.id)[0].status is AttemptStatus.RUNNING
    store.close()


def test_completed_study_can_be_loaded_without_reexecution(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "completed.sqlite")
    dataset = InMemoryDataset((2,), version="v1")
    first = optimizer_for(
        store,
        tmp_path,
        SequenceStrategy((Candidate({"multiplier": 2}),)),
        max_trials=1,
    )
    initial = asyncio.run(first.aoptimize(dataset, study_name="completed"))
    adapter = MultiplyingAdapter()
    strategy = SequenceStrategy(())
    resumed = optimizer_for(store, tmp_path, strategy, max_trials=1, adapter=adapter).resume(
        dataset, study_id=initial.study_id
    )

    assert resumed.stop_reason == "MaxTrials"
    assert resumed.best_candidate == Candidate({"multiplier": 2})
    assert resumed.usage.input_tokens == 1
    assert adapter.calls == 0
    assert strategy.observations == [Candidate({"multiplier": 2})]
    assert any(event.type == "study.stopping" for event in store.list_events(initial.study_id))
    store.close()


def test_resume_rejects_unknown_and_terminal_failed_studies(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "terminal.sqlite")
    dataset = InMemoryDataset((1,), version="v1")
    optimizer = optimizer_for(store, tmp_path, SequenceStrategy(()), max_trials=1)

    with pytest.raises(ResumeError, match="unknown"):
        asyncio.run(optimizer.aresume(dataset, study_id="missing"))

    study = store.create_study("failed", optimizer._study_configuration(dataset))
    store.transition_study(study.id, StudyStatus.FAILED)
    with pytest.raises(ResumeError, match="terminal"):
        asyncio.run(optimizer.aresume(dataset, study_id=study.id))
    store.close()


def test_resume_rejects_changed_strategy_fingerprint(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "fingerprint.sqlite")
    dataset = InMemoryDataset((1,), version="v1")
    space = SearchSpace({"multiplier": IntegerRange(1, 3)})

    def build(seed: int) -> Optimizer:
        return Optimizer(
            adapter=framework_fixture(MultiplyingAdapter()),
            strategy=RandomSearch(space, seed=seed),
            evaluators=[QualityEvaluator()],
            objective=Objective((ObjectiveTerm("quality"),)),
            store=store,
            settings=settings(tmp_path, max_trials=1),
            retry_policy=RetryPolicy(max_retries=0),
        )

    original = build(1)
    study = store.create_study("fingerprint", original._study_configuration(dataset))
    store.transition_study(study.id, StudyStatus.RUNNING)

    with pytest.raises(ResumeError, match="incompatible"):
        asyncio.run(build(2).aresume(dataset, study_id=study.id))
    store.close()


def test_replay_aware_strategy_receives_failed_and_unfinished_reservations(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "all-replay.sqlite")
    dataset = InMemoryDataset((1,), version="v1")

    def build(strategy: ReplayTrackingStrategy) -> Optimizer:
        return Optimizer(
            adapter=framework_fixture(MultiplyingAdapter()),
            strategy=strategy,
            evaluators=[QualityEvaluator()],
            objective=Objective((ObjectiveTerm("quality"),)),
            store=store,
            settings=settings(tmp_path, max_trials=3),
            retry_policy=RetryPolicy(max_retries=0),
        )

    original = build(ReplayTrackingStrategy(()))
    study = store.create_study("all-replay", original._study_configuration(dataset))
    store.transition_study(study.id, StudyStatus.RUNNING)
    failed = store.reserve_trial(study.id, Candidate({"multiplier": 1}))
    failed_attempt = store.start_attempt(failed.id, lease_seconds=10.0)
    store.commit_trial_result(
        failed.id,
        status=TrialStatus.FAILED,
        attempt_id=failed_attempt.id,
        error="adapter failed: RuntimeError",
    )
    store.reserve_trial(study.id, Candidate({"multiplier": 2}))
    strategy = ReplayTrackingStrategy((Candidate({"multiplier": 3}),))

    result = asyncio.run(build(strategy).aresume(dataset, study_id=study.id))

    assert strategy.replayed == [
        Candidate({"multiplier": 1}),
        Candidate({"multiplier": 2}),
    ]
    assert strategy.observations == [
        Candidate({"multiplier": 2}),
        Candidate({"multiplier": 3}),
    ]
    assert [trial.candidate for trial in result.trials] == [
        Candidate({"multiplier": 1}),
        Candidate({"multiplier": 2}),
        Candidate({"multiplier": 3}),
    ]
    store.close()
