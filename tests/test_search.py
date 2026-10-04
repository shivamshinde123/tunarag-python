import asyncio

import pytest

from tunarag.search import Categorical, FloatRange, IntegerRange, RandomSearch, SearchSpace


def test_seeded_random_search_is_reproducible() -> None:
    space = SearchSpace(
        {
            "top_k": IntegerRange(1, 5),
            "temperature": FloatRange(0.0, 1.0),
            "model": Categorical(("small", "large")),
        }
    )
    first = RandomSearch(space, seed=7)
    second = RandomSearch(space, seed=7)

    first_candidates = [asyncio.run(first.suggest()) for _ in range(5)]
    second_candidates = [asyncio.run(second.suggest()) for _ in range(5)]

    assert first_candidates == second_candidates
    assert all(1 <= candidate.parameters["top_k"] <= 5 for candidate in first_candidates)
    assert all(0.0 <= candidate.parameters["temperature"] <= 1.0 for candidate in first_candidates)


def test_search_space_rejects_invalid_ranges() -> None:
    with pytest.raises(ValueError, match="minimum"):
        IntegerRange(2, 1)
    with pytest.raises(ValueError, match="empty"):
        Categorical(())
    with pytest.raises(ValueError, match="at least one"):
        SearchSpace({})
