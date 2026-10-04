import random

from hypothesis import given
from hypothesis import strategies as st

from tunarag.search import FloatRange, IntegerRange, SearchSpace
from tunarag.serialization import canonical_json, content_hash, storage_json

_json_scalars = st.none() | st.booleans() | st.integers() | st.text()


@given(st.dictionaries(st.text(min_size=1), _json_scalars, max_size=20))
def test_canonical_identity_is_independent_of_mapping_insertion_order(
    values: dict[str, object],
) -> None:
    reversed_values = dict(reversed(tuple(values.items())))

    assert canonical_json(values) == canonical_json(reversed_values)
    assert content_hash(values) == content_hash(reversed_values)
    assert storage_json(values) == storage_json(reversed_values)


@given(
    minimum=st.integers(min_value=-10_000, max_value=10_000),
    width=st.integers(min_value=0, max_value=10_000),
    seed=st.integers(),
)
def test_integer_range_samples_and_validates_only_inclusive_values(
    minimum: int, width: int, seed: int
) -> None:
    maximum = minimum + width
    space = SearchSpace({"value": IntegerRange(minimum, maximum)})
    candidate = space.sample(random.Random(seed))

    assert minimum <= candidate.parameters["value"] <= maximum
    assert space.validate(candidate.parameters) == candidate


@given(
    minimum=st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False),
    width=st.floats(min_value=0.0, max_value=1e6, allow_nan=False, allow_infinity=False),
    seed=st.integers(),
)
def test_float_range_samples_and_validates_only_inclusive_values(
    minimum: float, width: float, seed: int
) -> None:
    maximum = minimum + width
    space = SearchSpace({"value": FloatRange(minimum, maximum)})
    candidate = space.sample(random.Random(seed))

    assert minimum <= candidate.parameters["value"] <= maximum
    assert space.validate(candidate.parameters) == candidate
