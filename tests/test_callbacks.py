import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tunarag import (
    CachePolicy,
    Candidate,
    InMemoryDataset,
    MetricValue,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RetryPolicy,
    Settings,
    SQLiteStore,
    StudyEvent,
    TrialStatus,
    UsageRecord,
)


class OneCandidateStrategy:
    async def suggest(self) -> Candidate:
        return Candidate({"value": 1})

    async def observe(
        self,
        candidate: Candidate,
        metrics: Sequence[MetricValue],
        usage: Sequence[UsageRecord],
    ) -> None:
        del candidate, metrics, usage


class Adapter:
    async def run(self, candidate: Candidate, example: Any) -> tuple[Any, Sequence[UsageRecord]]:
        del candidate
        return example, [UsageRecord("adapter", input_tokens=1)]


class Evaluator:
    async def evaluate(self, output: Any, example: Any) -> Sequence[MetricValue]:
        del example
        return [MetricValue("quality", float(output))]


class RecordingCallback:
    def __init__(self) -> None:
        self.events: list[StudyEvent] = []

    async def on_event(self, event: StudyEvent) -> None:
        self.events.append(event)


class FailingCallback:
    def __init__(self) -> None:
        self.calls = 0

    async def on_event(self, event: StudyEvent) -> None:
        del event
        self.calls += 1
        raise RuntimeError("private callback payload")


def settings(tmp_path: Path) -> Settings:
    return Settings.resolve(
        overrides={"home": tmp_path, "max_trials": 1, "cache_policy": CachePolicy.OFF},
        environ={},
    )


def optimizer(
    store: SQLiteStore,
    tmp_path: Path,
    callbacks: Sequence[Any],
) -> Optimizer:
    return Optimizer(
        adapter=Adapter(),
        strategy=OneCandidateStrategy(),
        evaluators=[Evaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=settings(tmp_path),
        retry_policy=RetryPolicy(max_retries=0),
        callbacks=callbacks,
    )


def test_callbacks_receive_durable_events_in_sequence_order(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "events.sqlite")
    callback = RecordingCallback()

    result = asyncio.run(
        optimizer(store, tmp_path, [callback]).aoptimize(
            InMemoryDataset((1,), version="v1"), study_name="events"
        )
    )

    assert result.trials[0].status is TrialStatus.SUCCEEDED
    assert [event.sequence for event in callback.events] == list(range(len(callback.events)))
    assert [event.type for event in callback.events] == [
        "study.created",
        "study.running",
        "trial.reserved",
        "trial.attempt.started",
        "trial.succeeded",
        "study.stopping",
        "study.completed",
    ]
    assert callback.events == store.list_events(result.study_id)
    store.close()


def test_callback_failures_are_durable_and_do_not_fail_optimization(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "callback-failure.sqlite")
    callback = FailingCallback()

    result = asyncio.run(
        optimizer(store, tmp_path, [callback]).aoptimize(
            InMemoryDataset((1,), version="v1"), study_name="failure"
        )
    )

    events = store.list_events(result.study_id)
    source_events = [event for event in events if event.type != "callback.failed"]
    failure_events = [event for event in events if event.type == "callback.failed"]
    assert result.trials[0].status is TrialStatus.SUCCEEDED
    assert callback.calls == len(source_events)
    assert len(failure_events) == len(source_events)
    assert all(event.payload["cause"] == "RuntimeError" for event in failure_events)
    assert "private callback payload" not in repr(failure_events)
    store.close()


def test_retry_event_is_dispatched_before_backoff(tmp_path) -> None:
    class FlakyAdapter:
        def __init__(self) -> None:
            self.calls = 0

        async def run(
            self, candidate: Candidate, example: Any
        ) -> tuple[Any, Sequence[UsageRecord]]:
            del candidate
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("temporary")
            return example, []

    store = SQLiteStore(tmp_path / "retry-callback.sqlite")
    callback = RecordingCallback()

    async def assert_dispatched(delay: float) -> None:
        del delay
        assert callback.events[-1].type == "trial.retry_scheduled"

    runner = Optimizer(
        adapter=FlakyAdapter(),
        strategy=OneCandidateStrategy(),
        evaluators=[Evaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=settings(tmp_path),
        retry_policy=RetryPolicy(max_retries=1),
        callbacks=[callback],
        sleeper=assert_dispatched,
    )

    result = asyncio.run(runner.aoptimize(InMemoryDataset((1,), version="v1"), study_name="retry"))

    assert result.trials[0].attempts == 2
    assert "trial.retry_scheduled" in [event.type for event in callback.events]
    store.close()
