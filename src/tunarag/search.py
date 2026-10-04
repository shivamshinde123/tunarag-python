"""Typed search spaces and the deterministic random strategy."""

import random
from dataclasses import dataclass
from typing import Any, Protocol

from .domain import Candidate


class Parameter(Protocol):
    """Sample one typed parameter value from a random stream."""

    def sample(self, generator: random.Random) -> Any: ...


@dataclass(frozen=True, slots=True)
class IntegerRange:
    """Inclusive integer range."""

    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        if self.minimum > self.maximum:
            raise ValueError("integer range minimum must not exceed maximum")

    def sample(self, generator: random.Random) -> int:
        return generator.randint(self.minimum, self.maximum)


@dataclass(frozen=True, slots=True)
class FloatRange:
    """Continuous float range."""

    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if self.minimum > self.maximum:
            raise ValueError("float range minimum must not exceed maximum")

    def sample(self, generator: random.Random) -> float:
        return generator.uniform(self.minimum, self.maximum)


@dataclass(frozen=True, slots=True)
class Categorical:
    """A non-empty collection of candidate values."""

    values: tuple[Any, ...]

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError("categorical values must not be empty")

    def sample(self, generator: random.Random) -> Any:
        return generator.choice(self.values)


@dataclass(frozen=True, slots=True)
class SearchSpace:
    """Named typed parameters from which candidates can be sampled."""

    parameters: dict[str, Parameter]

    def __post_init__(self) -> None:
        if not self.parameters:
            raise ValueError("search space must contain at least one parameter")
        if any(not name.strip() for name in self.parameters):
            raise ValueError("search-space parameter names must not be empty")
        object.__setattr__(self, "parameters", dict(self.parameters))

    def sample(self, generator: random.Random) -> Candidate:
        return Candidate(
            {name: parameter.sample(generator) for name, parameter in self.parameters.items()}
        )


class RandomSearch:
    """Seeded random strategy implementing the common search contract."""

    def __init__(self, space: SearchSpace, *, seed: int | None = None) -> None:
        self._space = space
        self._seed = seed
        self._generator = random.Random(seed)

    async def suggest(self) -> Candidate:
        return self._space.sample(self._generator)

    async def observe(self, candidate: Candidate, metrics: Any, usage: Any) -> None:
        del candidate, metrics, usage

    async def replay(self, candidate: Candidate, metrics: Any, usage: Any) -> None:
        """Advance and verify deterministic generator state during resume."""

        del metrics, usage
        expected = self._space.sample(self._generator)
        if expected != candidate:
            raise ValueError("persisted candidate does not match seeded random search state")

    def fingerprint(self) -> Any:
        """Return stable search-space and seed semantics."""

        return {"space": self._space, "seed": self._seed}
