import asyncio
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

from tunarag import (
    CacheEntry,
    CacheKey,
    CacheLookup,
    CacheLookupStatus,
    CachePolicy,
    CachePrivacy,
    Candidate,
    InMemoryDataset,
    MetricValue,
    Objective,
    ObjectiveTerm,
    Optimizer,
    RetryPolicy,
    Settings,
    SQLiteCache,
    SQLiteStore,
    TrialStatus,
    UsageRecord,
)


class SingleCandidateStrategy:
    def __init__(self, candidate: Candidate) -> None:
        self.candidate = candidate
        self.observed_usage: tuple[UsageRecord, ...] = ()

    async def suggest(self) -> Candidate:
        return self.candidate

    async def observe(
        self,
        candidate: Candidate,
        metrics: Sequence[MetricValue],
        usage: Sequence[UsageRecord],
    ) -> None:
        del candidate, metrics
        self.observed_usage = tuple(usage)


class QualityEvaluator:
    async def evaluate(self, output: Any, example: Any) -> Sequence[MetricValue]:
        del example
        return [MetricValue("quality", float(output))]


class PartialFlakyAdapter:
    def __init__(self) -> None:
        self.attempt = 0

    async def run(self, candidate: Candidate, example: Any) -> tuple[Any, Sequence[UsageRecord]]:
        del candidate
        if example == 1:
            self.attempt += 1
        if self.attempt == 1 and example == 2:
            raise ConnectionError("temporary provider outage")
        return example, [UsageRecord("adapter", input_tokens=1, cost=0.1)]


class CountingAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, candidate: Candidate, example: Any) -> tuple[Any, Sequence[UsageRecord]]:
        del candidate
        self.calls += 1
        return example, [UsageRecord("adapter", input_tokens=1, cost=0.1)]


class SemanticCorruptCache:
    def __init__(self) -> None:
        self.puts = 0

    def get(self, key: CacheKey) -> CacheLookup:
        return CacheLookup(key, CacheLookupStatus.HIT, payload=b"not-json")

    def put(
        self,
        key: CacheKey,
        payload: bytes | bytearray | memoryview,
        *,
        privacy: CachePrivacy = CachePrivacy.STANDARD,
        ttl_seconds: float | None = None,
    ) -> CacheEntry:
        del payload, ttl_seconds
        self.puts += 1
        return CacheEntry(key, "checksum", privacy, 0.0, None)


class PolicyProbeCache:
    def __init__(self) -> None:
        self.gets = 0
        self.puts = 0

    def get(self, key: CacheKey) -> CacheLookup:
        self.gets += 1
        return CacheLookup(key, CacheLookupStatus.MISS)

    def put(
        self,
        key: CacheKey,
        payload: bytes | bytearray | memoryview,
        *,
        privacy: CachePrivacy = CachePrivacy.STANDARD,
        ttl_seconds: float | None = None,
    ) -> CacheEntry:
        del payload, ttl_seconds
        self.puts += 1
        return CacheEntry(key, "checksum", privacy, 0.0, None)


def settings(tmp_path: Path, *, cache_policy: CachePolicy = CachePolicy.OFF) -> Settings:
    return Settings.resolve(
        overrides={"home": tmp_path, "max_trials": 1, "cache_policy": cache_policy},
        environ={},
    )


def test_transient_failure_retries_and_preserves_all_attempt_usage(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "retry.sqlite")
    strategy = SingleCandidateStrategy(Candidate({"model": "small"}))
    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    optimizer = Optimizer(
        adapter=PartialFlakyAdapter(),
        strategy=strategy,
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=settings(tmp_path),
        retry_policy=RetryPolicy(
            max_retries=1,
            sample_timeout_seconds=1.0,
            trial_timeout_seconds=5.0,
            base_delay_seconds=0.25,
            max_delay_seconds=0.25,
        ),
        sleeper=record_delay,
    )

    result = asyncio.run(
        optimizer.aoptimize(InMemoryDataset((1, 2), version="v1"), study_name="retry")
    )

    trial = result.trials[0]
    assert trial.status is TrialStatus.SUCCEEDED
    assert trial.attempts == 2
    assert len(trial.usage) == 3
    assert result.usage.exact_cost == pytest.approx(0.3)
    assert delays == [0.25]
    assert len(store.list_usage(trial.id)) == 3
    assert [attempt.status.value for attempt in store.list_attempts(trial.id)] == [
        "failed",
        "succeeded",
    ]
    assert strategy.observed_usage == trial.usage
    store.close()


def test_sample_timeout_retries_then_fails_trial(tmp_path) -> None:
    class HangingAdapter:
        async def run(
            self, candidate: Candidate, example: Any
        ) -> tuple[Any, Sequence[UsageRecord]]:
            del candidate, example
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

    async def no_delay(delay: float) -> None:
        del delay

    store = SQLiteStore(tmp_path / "sample-timeout.sqlite")
    optimizer = Optimizer(
        adapter=HangingAdapter(),
        strategy=SingleCandidateStrategy(Candidate({"model": "small"})),
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=settings(tmp_path),
        retry_policy=RetryPolicy(
            max_retries=1,
            sample_timeout_seconds=0.01,
            trial_timeout_seconds=1.0,
            base_delay_seconds=0.0,
            max_delay_seconds=0.0,
        ),
        sleeper=no_delay,
    )

    result = asyncio.run(
        optimizer.aoptimize(InMemoryDataset((1,), version="v1"), study_name="timeout")
    )

    assert result.trials[0].attempts == 2
    assert result.trials[0].error == "adapter failed: TimeoutError"
    store.close()


def test_trial_timeout_is_separate_from_sample_timeout(tmp_path) -> None:
    class SlowAdapter:
        async def run(
            self, candidate: Candidate, example: Any
        ) -> tuple[Any, Sequence[UsageRecord]]:
            del candidate
            await asyncio.sleep(0.02)
            return example, []

    store = SQLiteStore(tmp_path / "trial-timeout.sqlite")
    optimizer = Optimizer(
        adapter=SlowAdapter(),
        strategy=SingleCandidateStrategy(Candidate({"model": "small"})),
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        settings=settings(tmp_path),
        retry_policy=RetryPolicy(
            max_retries=0,
            sample_timeout_seconds=1.0,
            trial_timeout_seconds=0.01,
        ),
    )

    result = asyncio.run(
        optimizer.aoptimize(InMemoryDataset((1,), version="v1"), study_name="trial-timeout")
    )

    assert result.trials[0].error == "trial failed: TimeoutError"
    store.close()


def test_objective_failure_does_not_double_count_usage(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "objective-failure.sqlite")
    optimizer = Optimizer(
        adapter=CountingAdapter(),
        strategy=SingleCandidateStrategy(Candidate({"model": "small"})),
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("missing"),)),
        store=store,
        settings=settings(tmp_path),
        retry_policy=RetryPolicy(max_retries=0),
    )

    result = asyncio.run(
        optimizer.aoptimize(InMemoryDataset((1,), version="v1"), study_name="objective-failure")
    )

    trial = result.trials[0]
    assert trial.status is TrialStatus.FAILED
    assert trial.error == "objective failed: unavailable"
    assert len(trial.usage) == 1
    assert len(store.list_usage(trial.id)) == 1
    store.close()


def test_successful_evaluation_is_reused_from_cache_without_usage(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "cache-study.sqlite")
    cache = SQLiteCache(tmp_path / "cache.sqlite")
    adapter = CountingAdapter()
    dataset = InMemoryDataset((2,), version="dataset-v1")

    first = Optimizer(
        adapter=adapter,
        strategy=SingleCandidateStrategy(Candidate({"model": "small"})),
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        cache=cache,
        settings=settings(tmp_path, cache_policy=CachePolicy.READ_WRITE),
        retry_policy=RetryPolicy(max_retries=0),
    )
    first_result = asyncio.run(first.aoptimize(dataset, study_name="cache-write"))

    second = Optimizer(
        adapter=adapter,
        strategy=SingleCandidateStrategy(Candidate({"model": "small"})),
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        cache=cache,
        settings=settings(tmp_path, cache_policy=CachePolicy.READ_WRITE),
        retry_policy=RetryPolicy(max_retries=0),
    )
    second_result = asyncio.run(second.aoptimize(dataset, study_name="cache-read"))

    assert not first_result.trials[0].cached
    assert second_result.trials[0].cached
    assert adapter.calls == 1
    assert second_result.trials[0].usage == ()
    assert second_result.usage.input_tokens == 0
    cache.close()
    store.close()


@pytest.mark.parametrize(
    ("policy", "expected_gets", "expected_puts"),
    [
        (CachePolicy.OFF, 0, 0),
        (CachePolicy.READ_ONLY, 1, 0),
        (CachePolicy.WRITE_ONLY, 0, 1),
        (CachePolicy.READ_WRITE, 1, 1),
    ],
)
def test_cache_policy_controls_reads_and_writes(
    tmp_path, policy: CachePolicy, expected_gets: int, expected_puts: int
) -> None:
    store = SQLiteStore(tmp_path / f"{policy.value}.sqlite")
    cache = PolicyProbeCache()
    optimizer = Optimizer(
        adapter=CountingAdapter(),
        strategy=SingleCandidateStrategy(Candidate({"model": "small"})),
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        cache=cache,
        settings=settings(tmp_path, cache_policy=policy),
        retry_policy=RetryPolicy(max_retries=0),
    )

    asyncio.run(optimizer.aoptimize(InMemoryDataset((1,), version="v1"), study_name=policy.value))

    assert cache.gets == expected_gets
    assert cache.puts == expected_puts
    store.close()


def test_semantically_invalid_cache_payload_falls_back_and_is_replaced(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "bad-cache.sqlite")
    cache = SemanticCorruptCache()
    adapter = CountingAdapter()
    optimizer = Optimizer(
        adapter=adapter,
        strategy=SingleCandidateStrategy(Candidate({"model": "small"})),
        evaluators=[QualityEvaluator()],
        objective=Objective((ObjectiveTerm("quality"),)),
        store=store,
        cache=cache,
        settings=settings(tmp_path, cache_policy=CachePolicy.READ_WRITE),
        retry_policy=RetryPolicy(max_retries=0),
    )

    result = asyncio.run(
        optimizer.aoptimize(InMemoryDataset((1,), version="v1"), study_name="bad-cache")
    )

    assert result.trials[0].status is TrialStatus.SUCCEEDED
    assert not result.trials[0].cached
    assert adapter.calls == 1
    assert cache.puts == 1
    assert any(
        event.type == "trial.cache_decode_failed" for event in store.list_events(result.study_id)
    )
    store.close()
