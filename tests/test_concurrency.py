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
    UsageRecord,
)


class SequenceStrategy:
    def __init__(self, candidates: Sequence[Candidate]) -> None:
        self._candidates = iter(candidates)
        self.observed: list[Candidate] = []

    async def suggest(self) -> Candidate:
        return next(self._candidates)

    async def observe(
        self,
        candidate: Candidate,
        metrics: Sequence[MetricValue],
        usage: Sequence[UsageRecord],
    ) -> None:
        del metrics, usage
        self.observed.append(candidate)


class TrackingAdapter:
    def __init__(self) -> None:
        self.active = 0
        self.maximum = 0

    async def run(self, candidate: Candidate, example: Any) -> tuple[Any, Sequence[UsageRecord]]:
        self.active += 1
        self.maximum = max(self.maximum, self.active)
        await asyncio.sleep(0.01)
        self.active -= 1
        return candidate.parameters["value"] * example, []


class Evaluator:
    async def evaluate(self, output: Any, example: Any) -> Sequence[MetricValue]:
        del example
        return [MetricValue("quality", float(output))]


def settings(tmp_path: Path, *, trials: int, samples: int, max_trials: int) -> Settings:
    return Settings.resolve(
        overrides={
            "home": tmp_path,
            "concurrency": trials,
            "sample_concurrency": samples,
            "max_trials": max_trials,
            "cache_policy": CachePolicy.OFF,
        },
        environ={},
    )


def test_trial_concurrency_is_bounded_and_observation_order_is_deterministic(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "trials.sqlite")
    adapter = TrackingAdapter()
    candidates = tuple(Candidate({"value": value}) for value in range(1, 6))
    strategy = SequenceStrategy(candidates)
    runner = Optimizer(
        adapter=adapter,
        strategy=strategy,
        evaluators=[Evaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=settings(tmp_path, trials=2, samples=1, max_trials=5),
        retry_policy=RetryPolicy(max_retries=0),
    )

    result = asyncio.run(runner.aoptimize(InMemoryDataset((1,), version="v1"), study_name="trials"))

    assert adapter.maximum == 2
    assert [trial.candidate for trial in result.trials] == list(candidates)
    assert strategy.observed == list(candidates)
    assert len(store.list_trials(result.study_id)) == 5
    store.close()


def test_sample_concurrency_is_bounded(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "samples.sqlite")
    adapter = TrackingAdapter()
    runner = Optimizer(
        adapter=adapter,
        strategy=SequenceStrategy((Candidate({"value": 1}),)),
        evaluators=[Evaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=settings(tmp_path, trials=1, samples=3, max_trials=1),
        retry_policy=RetryPolicy(max_retries=0),
    )

    result = asyncio.run(
        runner.aoptimize(InMemoryDataset((1, 2, 3, 4, 5), version="v1"), study_name="samples")
    )

    assert adapter.maximum == 3
    assert result.best_trial is not None
    assert result.best_trial.objective is not None
    assert result.best_trial.objective.score == 3.0
    store.close()
