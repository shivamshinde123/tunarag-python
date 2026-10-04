import asyncio
from collections.abc import Mapping, Sequence
from typing import Any

import pytest

from tunarag import Candidate, MetricValue, SearchSpaceError, Secret
from tunarag.search import (
    Categorical,
    IntegerRange,
    LLMSearch,
    LLMSuggestionRequest,
    SearchSpace,
)


class SequenceProvider:
    def __init__(self, proposals: Sequence[Mapping[str, Any] | Exception]) -> None:
        self._proposals = iter(proposals)
        self.requests: list[LLMSuggestionRequest] = []

    async def suggest(self, request: LLMSuggestionRequest) -> Mapping[str, Any]:
        self.requests.append(request)
        proposal = next(self._proposals)
        if isinstance(proposal, Exception):
            raise proposal
        return proposal


def space() -> SearchSpace:
    return SearchSpace(
        {
            "top_k": IntegerRange(1, 10),
            "model": Categorical(("small", "large")),
        }
    )


def test_llm_search_retries_invalid_proposals_and_returns_valid_candidate() -> None:
    provider = SequenceProvider(
        [
            {"top_k": 4},
            {"top_k": 99, "model": "small"},
            {"top_k": 6, "model": "large"},
        ]
    )
    strategy = LLMSearch(space(), provider, max_suggestion_attempts=3, fallback=False)

    candidate = asyncio.run(strategy.suggest())

    assert candidate == Candidate({"top_k": 6, "model": "large"})
    assert [request.attempt_number for request in provider.requests] == [0, 1, 2]
    assert provider.requests[0].search_space["top_k"] == {
        "type": "integer",
        "minimum": 1,
        "maximum": 10,
    }


def test_llm_search_fallback_is_bounded_and_deterministic() -> None:
    first_provider = SequenceProvider([RuntimeError("private one"), {"invalid": True}])
    second_provider = SequenceProvider([RuntimeError("private two"), {"invalid": True}])
    first = LLMSearch(space(), first_provider, max_suggestion_attempts=2, fallback_seed=7)
    second = LLMSearch(space(), second_provider, max_suggestion_attempts=2, fallback_seed=7)

    assert asyncio.run(first.suggest()) == asyncio.run(second.suggest())
    assert len(first_provider.requests) == 2
    assert len(second_provider.requests) == 2


def test_llm_search_without_fallback_raises_redacted_structured_error() -> None:
    provider = SequenceProvider([RuntimeError("private provider text")])
    strategy = LLMSearch(space(), provider, max_suggestion_attempts=1, fallback=False)

    with pytest.raises(SearchSpaceError) as captured:
        asyncio.run(strategy.suggest())

    assert captured.value.details["causes"] == ["RuntimeError"]
    assert "private provider text" not in repr(captured.value.as_dict())


def test_observations_and_replay_are_supplied_to_later_requests() -> None:
    provider = SequenceProvider([{"top_k": 2, "model": "small"}])
    strategy = LLMSearch(space(), provider)
    prior = Candidate({"top_k": 1, "model": "large"})
    asyncio.run(strategy.replay(prior, (), ()))
    asyncio.run(strategy.observe(prior, (MetricValue("quality", 0.5),), ()))

    asyncio.run(strategy.suggest())

    request = provider.requests[0]
    assert request.suggestion_number == 1
    assert [item.candidate for item in request.observations] == [prior, prior]
    assert request.observations[1].metrics == (MetricValue("quality", 0.5),)


def test_provider_observations_are_recursively_redacted() -> None:
    provider = SequenceProvider([{"top_k": 2, "model": "small"}])
    strategy = LLMSearch(space(), provider)
    private = Candidate({"top_k": 1, "model": "large", "api_key": Secret("private")})
    asyncio.run(strategy.observe(private, (), ()))

    asyncio.run(strategy.suggest())

    observed = provider.requests[0].observations[0].candidate.parameters
    assert observed["api_key"] == "***redacted***"
    assert "private" not in repr(provider.requests[0])


@pytest.mark.parametrize("attempts", [0, -1, True])
def test_llm_search_rejects_invalid_attempt_limit(attempts: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        LLMSearch(space(), SequenceProvider(()), max_suggestion_attempts=attempts)
