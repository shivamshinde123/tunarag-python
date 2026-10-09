"""Typed search spaces and the deterministic random strategy."""

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol, cast

from .contracts import Fingerprintable
from .domain import Candidate, MetricValue, Secret, UsageRecord
from .errors import SearchSpaceError, redact


class Parameter(Protocol):
    """Sample one typed parameter value from a random stream."""

    def sample(self, generator: random.Random) -> Any: ...

    def accepts(self, value: Any) -> bool: ...

    def describe(self) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class IntegerRange:
    """Inclusive integer range."""

    minimum: int
    maximum: int

    def __post_init__(self) -> None:
        if any(
            isinstance(value, bool) or not isinstance(value, int)
            for value in (self.minimum, self.maximum)
        ):
            raise TypeError("integer range bounds must be integers")
        if self.minimum > self.maximum:
            raise ValueError("integer range minimum must not exceed maximum")

    def sample(self, generator: random.Random) -> int:
        return generator.randint(self.minimum, self.maximum)

    def accepts(self, value: Any) -> bool:
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and self.minimum <= value <= self.maximum
        )

    def describe(self) -> Mapping[str, Any]:
        return {"type": "integer", "minimum": self.minimum, "maximum": self.maximum}


@dataclass(frozen=True, slots=True)
class FloatRange:
    """Continuous float range."""

    minimum: float
    maximum: float

    def __post_init__(self) -> None:
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in (self.minimum, self.maximum)
        ):
            raise ValueError("float range bounds must be finite numbers")
        if self.minimum > self.maximum:
            raise ValueError("float range minimum must not exceed maximum")

    def sample(self, generator: random.Random) -> float:
        return generator.uniform(self.minimum, self.maximum)

    def accepts(self, value: Any) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and self.minimum <= value <= self.maximum
        )

    def describe(self) -> Mapping[str, Any]:
        return {"type": "number", "minimum": self.minimum, "maximum": self.maximum}


@dataclass(frozen=True, slots=True)
class Categorical:
    """A non-empty collection of candidate values."""

    values: tuple[Any, ...]

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError("categorical values must not be empty")

    def sample(self, generator: random.Random) -> Any:
        return generator.choice(self.values)

    def accepts(self, value: Any) -> bool:
        return value in self.values

    def describe(self) -> Mapping[str, Any]:
        return {
            "type": "categorical",
            "values": tuple(value for value in self.values if not isinstance(value, Secret)),
        }


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

    def validate(self, parameters: Mapping[str, Any]) -> Candidate:
        """Validate an exact candidate mapping against every parameter."""

        if set(parameters) != set(self.parameters):
            raise ValueError("candidate keys must exactly match the search space")
        for name, parameter in self.parameters.items():
            if not parameter.accepts(parameters[name]):
                raise ValueError(f"candidate value is outside the search space: {name}")
        return Candidate(dict(parameters))

    def describe(self) -> Mapping[str, Mapping[str, Any]]:
        """Return a provider-safe structured search-space description."""

        return {name: parameter.describe() for name, parameter in self.parameters.items()}


class RandomSearch:
    """Seeded random strategy implementing the common search contract."""

    def __init__(self, space: SearchSpace, *, seed: int | None = None) -> None:
        self._space = space
        self._seed = seed
        self._generator = random.Random(seed)
        self._replayed_candidates: list[Candidate] = []

    async def suggest(self) -> Candidate:
        return self._space.sample(self._generator)

    async def observe(self, candidate: Candidate, metrics: Any, usage: Any) -> None:
        del candidate, metrics, usage

    async def replay(self, candidate: Candidate, metrics: Any, usage: Any) -> None:
        """Advance and verify deterministic generator state during resume."""

        del metrics, usage
        if candidate in self._replayed_candidates:
            raise ValueError("persisted candidate does not match seeded random search state")
        for _ in range(10_000):
            expected = self._space.sample(self._generator)
            if expected == candidate:
                self._replayed_candidates.append(candidate)
                return
            if expected not in self._replayed_candidates:
                break
        raise ValueError("persisted candidate does not match seeded random search state")

    def fingerprint(self) -> Any:
        """Return stable search-space and seed semantics."""

        return {"space": self._space, "seed": self._seed}


@dataclass(frozen=True, slots=True)
class SearchObservation:
    """A prior reserved candidate and any committed metrics."""

    candidate: Candidate
    metrics: tuple[MetricValue, ...]


@dataclass(frozen=True, slots=True)
class LLMSuggestionRequest:
    """Provider-neutral structured input for one suggestion attempt."""

    search_space: Mapping[str, Mapping[str, Any]]
    observations: tuple[SearchObservation, ...]
    suggestion_number: int
    attempt_number: int


class LLMSearchProvider(Protocol):
    """Produce one structured candidate proposal without provider coupling."""

    async def suggest(self, request: LLMSuggestionRequest) -> Mapping[str, Any]: ...


class LLMSearch:
    """Validate bounded provider suggestions with deterministic random fallback."""

    def __init__(
        self,
        space: SearchSpace,
        provider: LLMSearchProvider,
        *,
        max_suggestion_attempts: int = 3,
        fallback_seed: int = 0,
        fallback: bool = True,
    ) -> None:
        if (
            not isinstance(max_suggestion_attempts, int)
            or isinstance(max_suggestion_attempts, bool)
            or max_suggestion_attempts < 1
        ):
            raise ValueError("maximum suggestion attempts must be positive")
        self._space = space
        self._provider = provider
        self._max_suggestion_attempts = max_suggestion_attempts
        self._fallback_seed = fallback_seed
        self._fallback = fallback
        self._suggestion_number = 0
        self._observations: list[SearchObservation] = []

    async def suggest(self) -> Candidate:
        causes: list[str] = []
        for attempt_number in range(self._max_suggestion_attempts):
            request = LLMSuggestionRequest(
                self._space.describe(),
                tuple(_provider_observation(item) for item in self._observations),
                self._suggestion_number,
                attempt_number,
            )
            try:
                proposal = await self._provider.suggest(request)
                candidate = self._space.validate(proposal)
            except Exception as error:
                causes.append(type(error).__name__)
                continue
            self._suggestion_number += 1
            return candidate
        if self._fallback:
            generator = random.Random(f"{self._fallback_seed}:{self._suggestion_number}")
            candidate = self._space.sample(generator)
            self._suggestion_number += 1
            return candidate
        raise SearchSpaceError(
            "LLM search exhausted invalid suggestion attempts",
            stage="strategy.suggest",
            details={"causes": causes, "attempts": self._max_suggestion_attempts},
        )

    async def observe(
        self,
        candidate: Candidate,
        metrics: Sequence[MetricValue],
        usage: Sequence[UsageRecord],
    ) -> None:
        del usage
        self._observations.append(SearchObservation(candidate, tuple(metrics)))

    async def replay(
        self,
        candidate: Candidate,
        metrics: Sequence[MetricValue],
        usage: Sequence[UsageRecord],
    ) -> None:
        del usage
        self._suggestion_number += 1
        self._observations.append(SearchObservation(candidate, tuple(metrics)))

    def fingerprint(self) -> Any:
        provider_type = type(self._provider)
        provider: dict[str, Any] = {
            "type": f"{provider_type.__module__}.{provider_type.__qualname__}"
        }
        if isinstance(self._provider, Fingerprintable):
            provider["fingerprint"] = self._provider.fingerprint()
        return {
            "space": self._space,
            "provider": provider,
            "max_suggestion_attempts": self._max_suggestion_attempts,
            "fallback_seed": self._fallback_seed,
            "fallback": self._fallback,
        }


def _provider_observation(observation: SearchObservation) -> SearchObservation:
    parameters = cast(dict[str, Any], redact(observation.candidate.parameters))
    return SearchObservation(Candidate(parameters), observation.metrics)
