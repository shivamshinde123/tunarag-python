"""Protocols implemented by user-owned RAG systems and package extensions."""

from collections.abc import AsyncIterator, Sequence
from typing import Any, Protocol

from .cache import CacheEntry, CacheKey, CacheLookup, CachePrivacy
from .domain import Candidate, MetricValue, UsageRecord


class RAGAdapter(Protocol):
    """Execute a user's RAG system for one candidate and example."""

    async def run(
        self, candidate: Candidate, example: Any
    ) -> tuple[Any, Sequence[UsageRecord]]: ...


class Dataset(Protocol):
    """Provide versioned evaluation examples."""

    @property
    def version(self) -> str: ...

    def __aiter__(self) -> AsyncIterator[Any]: ...


class Evaluator(Protocol):
    """Convert an adapter output and example into metric observations."""

    async def evaluate(self, output: Any, example: Any) -> Sequence[MetricValue]: ...


class SearchStrategy(Protocol):
    """Suggest candidates and observe completed trials."""

    async def suggest(self) -> Candidate: ...

    async def observe(
        self,
        candidate: Candidate,
        metrics: Sequence[MetricValue],
        usage: Sequence[UsageRecord],
    ) -> None: ...


class Cache(Protocol):
    """Persist and retrieve versioned semantic results."""

    def get(self, key: CacheKey) -> CacheLookup: ...

    def put(
        self,
        key: CacheKey,
        payload: bytes | bytearray | memoryview,
        *,
        privacy: CachePrivacy = CachePrivacy.STANDARD,
        ttl_seconds: float | None = None,
    ) -> CacheEntry: ...
