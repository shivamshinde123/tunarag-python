"""Repeatable in-memory evaluation datasets."""

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class InMemoryDataset:
    """A versioned, repeatable dataset backed by an immutable tuple."""

    examples: tuple[Any, ...]
    version: str

    def __post_init__(self) -> None:
        if not self.examples:
            raise ValueError("dataset must contain at least one example")
        if not self.version.strip():
            raise ValueError("dataset version must not be empty")

    @classmethod
    def from_iterable(cls, examples: Iterable[Any], *, version: str) -> "InMemoryDataset":
        """Materialize a repeatable dataset from an iterable."""

        return cls(tuple(examples), version)

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._iterate()

    async def _iterate(self) -> AsyncIterator[Any]:
        for example in self.examples:
            yield example
